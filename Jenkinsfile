// =============================================================================
// VirtualAssist Connect — Jenkins CI Pipeline
//
// Strategy:
//   - Docker is used for REPRODUCIBLE TEST ISOLATION only.
//   - Deployment artifacts are ZIP packages (not container images).
//   - Each Lambda is built, linted, and tested in its own Docker container.
//
// Required Jenkins plugins:
//   - Docker Pipeline
//   - JUnit / Cobertura (for test reporting)
//
// Required environment:
//   - Jenkins agent must have Docker installed and access to the Docker daemon.
// =============================================================================

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        // Lambdas to build — add new entries here as the project grows.
        LAMBDAS = 'hello-world calculator sre-platform'
        LAMBDA_BASE_PATH = 'backend/lambdas'
        LAYER_PATH = 'backend/lambda-layer'
        ARTIFACTS_DIR = 'dist'
    }

    stages {

        // ── 1. Checkout ───────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                echo "Branch: ${env.BRANCH_NAME ?: 'local'} | Commit: ${env.GIT_COMMIT?.take(8) ?: 'unknown'}"
            }
        }

        // ── 2. Build CI Images ────────────────────────────────────────────────
        // Builds a Docker image per Lambda using the project root as context.
        // The image includes: deps, shared layer, src, and tests.
        stage('Build CI Images') {
            steps {
                script {
                    env.LAMBDAS.split(' ').each { lambda ->
                        echo "Building CI image for: ${lambda}"
                        sh """
                            docker build \
                                -f ${env.LAMBDA_BASE_PATH}/${lambda}/Dockerfile \
                                -t lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                .
                        """
                    }
                }
            }
        }

        // ── 3. Lint ───────────────────────────────────────────────────────────
        // Runs flake8 inside the Docker CI image. No side effects on host.
        stage('Lint') {
            steps {
                script {
                    env.LAMBDAS.split(' ').each { lambda ->
                        echo "Linting: ${lambda}"
                        sh """
                            docker run --rm --entrypoint "" \
                                lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                bash -c "pip install flake8 --quiet && flake8 src/ --max-line-length=120 --exclude=__pycache__"
                        """
                    }
                }
            }
        }

        // ── 4. Test (inside Docker) ───────────────────────────────────────────
        // Runs pytest inside each Lambda's CI image, capturing JUnit XML + coverage.
        stage('Test') {
            steps {
                script {
                    env.LAMBDAS.split(' ').each { lambda ->
                        echo "Testing: ${lambda}"
                        sh """
                            mkdir -p ${env.ARTIFACTS_DIR}/${lambda}
                            docker run --rm --entrypoint "" \
                                -v \$(pwd)/${env.ARTIFACTS_DIR}/${lambda}:/tmp/reports \
                                -e AWS_DEFAULT_REGION=us-east-1 \
                                -e AWS_ACCESS_KEY_ID=test \
                                -e AWS_SECRET_ACCESS_KEY=test \
                                lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                bash -c "
                                    cd \${LAMBDA_TASK_ROOT} &&
                                    pytest tests/ \
                                        --junitxml=/tmp/reports/junit.xml \
                                        --cov=src \
                                        --cov-report=xml:/tmp/reports/coverage.xml \
                                        --cov-report=term \
                                        -m 'not integration'
                                "
                        """
                    }
                }
            }
            post {
                always {
                    // Publish JUnit results for each Lambda.
                    junit allowEmptyResults: true,
                          testResults: "${env.ARTIFACTS_DIR}/**/junit.xml"
                    // Publish coverage — requires Cobertura or similar plugin.
                    publishHTML(target: [
                        allowMissing: true,
                        reportDir: "${env.ARTIFACTS_DIR}",
                        reportFiles: '**/coverage.xml',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }

        // ── 5. Package ZIP ────────────────────────────────────────────────────
        // Creates a deployment ZIP per Lambda: src/ + shared layer.
        // This is what gets deployed to AWS Lambda (not the Docker image).
        stage('Package ZIP') {
            steps {
                script {
                    env.LAMBDAS.split(' ').each { lambda ->
                        echo "Packaging ZIP for: ${lambda}"
                        sh """
                            # Clean up old build
                            rm -rf /tmp/lambda-build-${lambda}
                            mkdir -p /tmp/lambda-build-${lambda}

                            # Copy application source
                            cp -r ${env.LAMBDA_BASE_PATH}/${lambda}/src/ \
                                /tmp/lambda-build-${lambda}/

                            # Copy shared layer (mirrors the AWS Lambda Layer)
                            cp -r ${env.LAYER_PATH}/python/ \
                                /tmp/lambda-build-${lambda}/

                            # Copy any additional config files
                            [ -f ${env.LAMBDA_BASE_PATH}/${lambda}/incident_config.json ] && \
                                cp ${env.LAMBDA_BASE_PATH}/${lambda}/incident_config.json \
                                /tmp/lambda-build-${lambda}/ || true

                            # Install runtime-only deps (exclude test packages)
                            pip install \
                                --target /tmp/lambda-build-${lambda} \
                                --require-hashes --no-cache-dir 2>/dev/null || \
                            pip install \
                                -r ${env.LAMBDA_BASE_PATH}/${lambda}/requirements.txt \
                                --target /tmp/lambda-build-${lambda} \
                                --no-cache-dir

                            # Create the ZIP artifact
                            mkdir -p ${env.ARTIFACTS_DIR}/${lambda}
                            cd /tmp/lambda-build-${lambda} && \
                                zip -r \$(pwd)/../../../${env.ARTIFACTS_DIR}/${lambda}/${lambda}-\${BUILD_NUMBER}.zip . -x '*.pyc' -x '*/__pycache__/*' -x '*/test_*.py' -x '*/tests/*'
                        """
                    }
                }
            }
        }

        // ── 6. Archive Artifacts ──────────────────────────────────────────────
        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: "${env.ARTIFACTS_DIR}/**/*.zip",
                                 fingerprint: true,
                                 allowEmptyArchive: false
                echo 'ZIP packages archived. Ready for deployment via CDK/Terraform.'
            }
        }
    }

    // ── Post-pipeline Cleanup ─────────────────────────────────────────────────
    post {
        always {
            script {
                // Remove CI Docker images to keep the agent clean.
                env.LAMBDAS.split(' ').each { lambda ->
                    sh "docker rmi lambda-${lambda}-ci:${env.BUILD_NUMBER} --force 2>/dev/null || true"
                }
            }
        }
        success {
            echo "✅ Pipeline SUCCESS — ZIP artifacts ready in ${env.ARTIFACTS_DIR}/"
        }
        failure {
            echo "❌ Pipeline FAILED — check stage logs above."
        }
    }
}
