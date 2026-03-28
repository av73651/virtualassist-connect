FROM public.ecr.aws/lambda/python:3.12

# Copy requirements file
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install the specified packages
RUN pip install -r requirements.txt

# Copy function code
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Set the CMD to your handler
CMD ["src.handlers.hello_handler.lambda_handler"]
