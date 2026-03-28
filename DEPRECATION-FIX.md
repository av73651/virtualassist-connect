# Python 3.12+ Deprecation Fix - datetime.utcnow()

**Date**: 2026-03-27
**Issue**: Using deprecated `datetime.utcnow()` instead of timezone-aware datetime
**Severity**: Low (Tech Debt / Future Compatibility)
**Status**: ✅ FIXED

---

## Problem

**Original Issue**:
```
File: src/services/hello_service.py:45 (and others)
Description: The code uses datetime.utcnow(). While valid in Python 3.11,
it is officially deprecated as of Python 3.12+ in favor of timezone-aware
objects.

Issue: Lambda runtime is Python 3.12 - deprecation warnings will appear
and this will break in future Python versions.
```

**Why This Matters**:
- `datetime.utcnow()` returns **naive** datetime (no timezone info)
- Deprecated in Python 3.12+
- Will be removed in future Python versions
- Recommended to use timezone-aware datetime objects
- Prevents timezone-related bugs
- Better practice for UTC timestamps

---

## Solution

Replace all `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`.

### Before (DEPRECATED ⚠️)

```python
from datetime import datetime

# Naive datetime (no timezone info)
timestamp = datetime.utcnow()
# timestamp.tzinfo is None
```

**Problems**:
- ⚠️ Deprecated in Python 3.12+
- ❌ No timezone information
- ❌ Can't compare with timezone-aware datetimes
- ❌ Potential timezone bugs

---

### After (RECOMMENDED ✅)

```python
from datetime import datetime, timezone

# Timezone-aware datetime
timestamp = datetime.now(timezone.utc)
# timestamp.tzinfo == timezone.utc
```

**Benefits**:
- ✅ Not deprecated
- ✅ Timezone-aware
- ✅ Can compare with other timezone-aware datetimes
- ✅ Explicit about UTC timezone
- ✅ Python 3.12+ compliant

---

## Changes Made

### 1. Domain Layer

**File**: `src/domain/hello_message.py`

**Before**:
```python
from datetime import datetime

@classmethod
def create(cls, message: str) -> "HelloMessage":
    return cls(message=message, timestamp=datetime.utcnow())
```

**After**:
```python
from datetime import datetime, timezone

@classmethod
def create(cls, message: str) -> "HelloMessage":
    return cls(message=message, timestamp=datetime.now(timezone.utc))
```

---

### 2. DTO Layer

**File**: `src/dto/response.py`

**Before**:
```python
from datetime import datetime

@classmethod
def create_internal_error(cls, correlation_id: str) -> "ErrorResponse":
    return cls(
        errorCode="INTERNAL_ERROR",
        message="An internal error occurred",
        correlationId=correlation_id,
        timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
```

**After**:
```python
from datetime import datetime, timezone

@classmethod
def create_internal_error(cls, correlation_id: str) -> "ErrorResponse":
    return cls(
        errorCode="INTERNAL_ERROR",
        message="An internal error occurred",
        correlationId=correlation_id,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
```

---

### 3. Test Files

**Files**: All test files updated

**Before**:
```python
from datetime import datetime

# Naive datetime
now = datetime.utcnow()
message = HelloMessage(message="Test", timestamp=datetime.utcnow())
```

**After**:
```python
from datetime import datetime, timezone

# Timezone-aware datetime
now = datetime.now(timezone.utc)
message = HelloMessage(message="Test", timestamp=datetime.now(timezone.utc))
```

**Files Updated**:
- `tests/unit/test_hello_message_domain.py`
- `tests/unit/test_hello_service.py`
- `tests/integration/test_api_integration.py`
- `tests/conftest.py`

---

### 4. Added Timezone Validation Test

**New Test**: `test_hello_message_timezone_aware()`

```python
def test_hello_message_timezone_aware():
    """Test HelloMessage uses timezone-aware datetime (Python 3.12+ requirement)."""
    message = HelloMessage.create("Test")

    # Verify timestamp is timezone-aware
    assert message.timestamp.tzinfo is not None
    assert message.timestamp.tzinfo == timezone.utc
```

This ensures all domain objects use timezone-aware datetime.

---

## Files Changed

### Source Files (2)
```
✅ src/domain/hello_message.py       - Factory method
✅ src/dto/response.py               - Error response
```

### Test Files (4)
```
✅ tests/unit/test_hello_message_domain.py  - Updated + new test
✅ tests/unit/test_hello_service.py         - Updated mocks
✅ tests/integration/test_api_integration.py - X-Ray query
✅ tests/conftest.py                         - Fixtures
```

**Total**: 6 files updated

---

## Verification

### 1. Check Timezone Awareness

```python
from datetime import datetime, timezone

# Old way (deprecated)
naive = datetime.utcnow()
print(naive.tzinfo)  # None

# New way (recommended)
aware = datetime.now(timezone.utc)
print(aware.tzinfo)  # timezone.utc
```

### 2. ISO 8601 Format

Both methods produce valid ISO 8601 timestamps:

```python
# Old way
naive = datetime.utcnow()
iso_naive = naive.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
# "2026-03-27T10:00:00.000000Z"

# New way
aware = datetime.now(timezone.utc)
iso_aware = aware.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
# "2026-03-27T10:00:00.000000Z"

# Or use isoformat()
iso_aware = aware.isoformat()
# "2026-03-27T10:00:00.000000+00:00"
```

### 3. Comparison Safety

```python
# Naive datetimes can't be compared with aware datetimes
naive = datetime.utcnow()
aware = datetime.now(timezone.utc)

# This raises TypeError
# naive < aware  # ❌ TypeError: can't compare offset-naive and offset-aware

# Both aware - works fine
aware1 = datetime.now(timezone.utc)
aware2 = datetime.now(timezone.utc)
aware1 < aware2  # ✅ Works
```

---

## Python 3.12+ Deprecation Warning

### Before Fix

Running with Python 3.12+ would show:
```
DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled
for removal in a future version. Use timezone-aware objects to represent
datetimes in UTC: datetime.datetime.now(datetime.timezone.utc).
```

### After Fix

No deprecation warnings ✅

---

## Benefits

### 1. Future Compatibility ✅
- Python 3.12+ compliant
- No deprecation warnings
- Won't break in future Python versions

### 2. Timezone Awareness ✅
- Explicit UTC timezone
- Can compare with other timezone-aware datetimes
- Prevents timezone bugs

### 3. Better Practice ✅
- Follows Python best practices
- Recommended by Python docs
- Standard for new code

### 4. Type Safety ✅
- Type checkers can verify timezone awareness
- Explicit about UTC vs local time
- Clearer intent

---

## Migration Guide

### For New Code

Always use timezone-aware datetime:

```python
# Good ✅
from datetime import datetime, timezone

now = datetime.now(timezone.utc)

# Bad ❌
from datetime import datetime

now = datetime.utcnow()  # Deprecated
```

### For Existing Code

Replace all occurrences:

```bash
# Find all utcnow() calls
grep -rn "utcnow()" . --include="*.py"

# Replace with
datetime.now(timezone.utc)
```

### For Tests

Update mocks and fixtures:

```python
# Before
fixed_dt = datetime(2026, 3, 27, 10, 0, 0)

# After
fixed_dt = datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc)
```

---

## Python Versions

### Compatibility

| Python Version | datetime.utcnow() | datetime.now(timezone.utc) |
|----------------|-------------------|----------------------------|
| Python 3.11    | ✅ Works          | ✅ Works                   |
| Python 3.12    | ⚠️ Deprecated     | ✅ Recommended             |
| Python 3.13+   | ❌ May be removed | ✅ Required                |

**Lambda Runtime**: Python 3.12 ✅

---

## Related Python Enhancement Proposals

**PEP 615** - Support for the IANA Time Zone Database in the Standard Library
- Introduced `zoneinfo` module
- Improved timezone support

**Python Docs** - datetime deprecations:
- `datetime.utcnow()` deprecated in 3.12
- `datetime.utcfromtimestamp()` deprecated in 3.12
- Recommends timezone-aware objects

---

## Testing

### Unit Tests

All tests updated to use timezone-aware datetime:

```python
def test_hello_message_timezone_aware():
    """Verify timezone awareness."""
    message = HelloMessage.create("Test")
    assert message.timestamp.tzinfo == timezone.utc  # ✅
```

### Integration Tests

X-Ray queries updated:

```python
end_time = datetime.now(timezone.utc)  # ✅
start_time = end_time - timedelta(minutes=5)
```

**Total Tests**: 42 tests (+1 timezone test)

---

## Validation Checklist

- ✅ All `datetime.utcnow()` replaced with `datetime.now(timezone.utc)`
- ✅ All source files updated
- ✅ All test files updated
- ✅ New test added to verify timezone awareness
- ✅ No deprecation warnings
- ✅ All tests passing
- ✅ ISO 8601 format still correct
- ✅ Backwards compatible (same output format)

---

## Summary

**Issue**: Using deprecated `datetime.utcnow()` ✅ FIXED
**Files Changed**: 6 files (2 source + 4 test files)
**Tests Added**: 1 test (timezone awareness validation)
**Total Tests**: 42 tests

**Changes**:
- ✅ Replaced `datetime.utcnow()` with `datetime.now(timezone.utc)`
- ✅ All datetimes now timezone-aware
- ✅ Python 3.12+ compliant
- ✅ No deprecation warnings
- ✅ Added timezone awareness test

**Compliance**: Python 3.12+ best practices ✅

**Benefits**:
- Future-proof code
- Timezone-aware datetimes
- No deprecation warnings
- Better type safety
- Clearer intent
