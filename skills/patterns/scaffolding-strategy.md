# AI Scaffolding Strategy 

## Purpose
Native OpenTelemetry (OTel), Hexagonal Clean Architecture layers, and Strict Python 3.12 Typing demand rigorous boilerplate. Manually writing this boilerplate causes **developer fatigue** and introduces critical bugs (such as broken trace contexts). Furthermore, duplicating boilerplate across identical Microservices causes extreme drift.

## The Rule: Developers MUST NOT write boilerplate.

To enforce consistent architecture, human developers are **forbidden** from manually creating the directory structures, OTel context managers, or base AWS CDK stacks by hand.

1. **Invoke the Machine**: Developers must use the `Code Generation` AI Skill to bootstrap every new feature.
2. **Review the Output**: Developers should act as code *reviewers* and logic *implementers*, verifying the generated architectural scaffolding.

## Standard Shared Architecture (Monorepo Bundling)
To prevent drift across lambdas, any cross-cutting code MUST live in `backend/shared/`.
Do **NOT** copy these into individual lambda `src/` directories.

1. `backend/shared/src/middleware/api_gateway.py` (Contains the `@api_gateway_handler` decorator for centralized JSON error mapping and trace injection).
2. `backend/shared/src/config/logging_config.py` (Contains standard Python `logging` configuration — JSON-formatted, OTel trace_id injected via `extra={}` fields — **do NOT use `structlog`**).

## Instruction to the Code Generation Skill
When generating a new endpoint or service, the AI Agent must strictly scope outputs to `backend/lambdas/{resource}/`.

1. **Domain & Services**: Generate `src/handlers/{action}_{resource}.py` which imports the shared `@api_gateway_handler`.
2. **DTOs**: `src/dto/{resource}_request.py` containing Pydantic models.
3. **Services**: `src/services/{resource}_service.py` containing pure domain logic wrapped in OTel metrics (`tracer.start_as_current_span()`).
4. **Docs & Plans**: `docs/{resource}-app-design.md`, `docs/{resource}-infra-design.md`, and an isolated `README.md` and `implementation-plan.md` MUST GO INTO the top-level `docs/specs/{service-name}/` directory.
5. **Infrastructure**: `infra/stacks/{resource}_stack.py` should configure the AWS CDK to bundle the Lambda `src` local code along with the `backend/shared/` module into a single deployment payload.

*Humans should only be filling in the pure business algorithms inside the `Service` layer, allowing the Code Generation AI to absorb the operational complexity.*
