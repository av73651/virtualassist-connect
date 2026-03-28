# Calculator Multi-Operator Enhancement - Workflows

**Date**: 2026-03-28

---

## Workflow: Perform Subtraction
**Steps**:
1. API Consumer sends POST request to /calculator/subtract with JSON body containing "a" and "b"
2. API Gateway receives request and invokes Lambda function
3. Lambda handler extracts trace ID from headers
4. Handler validates request body (both fields present and numeric)
5. Handler delegates to Calculator Service subtract method
6. Service performs subtraction operation (a - b)
7. Service returns domain object (Calculation with operation="subtract")
8. Handler converts domain object to DTO
9. Handler returns HTTP 200 with JSON response
10. API Gateway returns response to consumer

## Workflow: Perform Multiplication
**Steps**:
1. API Consumer sends POST request to /calculator/multiply with JSON body containing "a" and "b"
2. API Gateway receives request and invokes Lambda function
3. Lambda handler extracts trace ID from headers
4. Handler validates request body (both fields present and numeric)
5. Handler delegates to Calculator Service multiply method
6. Service performs multiplication operation (a * b)
7. Service returns domain object (Calculation with operation="multiply")
8. Handler converts domain object to DTO
9. Handler returns HTTP 200 with JSON response
10. API Gateway returns response to consumer

## Workflow: Perform Division (Happy Path)
**Steps**:
1. API Consumer sends POST request to /calculator/divide with JSON body containing "a" and "b"
2. API Gateway receives request and invokes Lambda function
3. Lambda handler extracts trace ID from headers
4. Handler validates request body (both fields present and numeric)
5. Handler delegates to Calculator Service divide method
6. Service validates divisor is not zero
7. Service performs division operation (a / b)
8. Service returns domain object (Calculation with operation="divide")
9. Handler converts domain object to DTO
10. Handler returns HTTP 200 with JSON response
11. API Gateway returns response to consumer

## Workflow: Division by Zero Error
**Steps**:
1. API Consumer sends POST request to /calculator/divide with b=0
2. API Gateway receives request and invokes Lambda function
3. Lambda handler validates request body (passes - both fields present and numeric)
4. Handler delegates to Calculator Service divide method
5. Service detects divisor is zero
6. Service raises domain error (division by zero)
7. Handler catches domain error
8. Handler returns HTTP 400 with error response (errorCode: "DIVISION_BY_ZERO")
9. API Gateway returns error response to consumer
