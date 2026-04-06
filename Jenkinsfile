// =============================================================================
// VirtualAssist Connect — Jenkins CI Pipeline (Enhanced)
//
// Strategy:
//   - Docker is used for REPRODUCIBLE TEST ISOLATION (including packaging).
//   - Deployment artifacts are ZIP packages (not container images).
//   - Each Lambda is built, linted, tested, and packaged in its own Docker container.
//   - Parallel execution for performance.
//
// Required Jenkins plugins:
//   - Docker Pipeline
//   - JUnit / Cobertura (for test reporting)
//   - Pipeline: Stage View (for parallel visualization)
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
        SHARED_PATH = 'backend/shared'
        ARTIFACTS_DIR = 'dist'
        COVERAGE_THRESHOLD = '80'
    }

    stages {

        // ── 1. Checkout ───────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                echo "Branch: ${env.BRANCH_NAME ?: 'local'} | Commit: ${env.GIT_COMMIT?.take(8) ?: 'unknown'}"
            }
        }

        // ── 2. Build CI Images (Parallel) ─────────────────────────────────────
        // Builds a Docker image per Lambda using the project root as context.
        // The image includes: deps, shared layer, src, and tests.
        stage('Build CI Images') {
            steps {
                script {
                    def parallelBuilds = [:]

                    env.LAMBDAS.split(' ').each { lambda ->
                        parallelBuilds[lambda] = {
                            stage("Build ${lambda}") {
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

                    parallel parallelBuilds
                }
            }
        }

        // ── 3. Quality Checks (Parallel: Lint + Security) ─────────────────────
        stage('Quality Checks') {
            parallel {
                stage('Lint') {
                    steps {
                        script {
                            def parallelLint = [:]

                            env.LAMBDAS.split(' ').each { lambda ->
                                parallelLint[lambda] = {
                                    echo "Linting: ${lambda}"
                                    sh """
                                        docker run --rm --entrypoint "" \
                                            -v \$(pwd)/.flake8:/app/.flake8:ro \
                                            lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                            bash -c "
                                                pip install flake8 --quiet
                                                cd \${LAMBDA_TASK_ROOT}
                                                flake8 src/
                                            "
                                    """
                                }
                            }

                            parallel parallelLint
                        }
                    }
                }

                stage('Security Scan') {
                    steps {
                        script {
                            def parallelSecurity = [:]

                            env.LAMBDAS.split(' ').each { lambda ->
                                parallelSecurity[lambda] = {
                                    echo "Security scanning: ${lambda}"
                                    sh """
                                        mkdir -p ${env.ARTIFACTS_DIR}/${lambda}
                                        docker run --rm --entrypoint "" \
                                            -v \$(pwd)/${env.ARTIFACTS_DIR}/${lambda}:/tmp/reports \
                                            lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                            bash -c "
                                                pip install safety bandit --quiet

                                                # Safety check for dependency vulnerabilities
                                                safety check --json > /tmp/reports/safety.json || true

                                                # Bandit check for security issues in code
                                                cd \${LAMBDA_TASK_ROOT}
                                                bandit -r src/ -f json -o /tmp/reports/bandit.json || true

                                                # Human-readable reports
                                                safety check || true
                                                bandit -r src/ -ll || true
                                            "
                                    """
                                }
                            }

                            parallel parallelSecurity
                        }
                    }
                }
            }
        }

        // ── 4. Test (Parallel) ────────────────────────────────────────────────
        // Runs pytest inside each Lambda's CI image, capturing JUnit XML + coverage.
        stage('Unit Tests') {
            steps {
                script {
                    def parallelTests = [:]

                    env.LAMBDAS.split(' ').each { lambda ->
                        parallelTests[lambda] = {
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
                                        cd \${LAMBDA_TASK_ROOT}
                                        pytest tests/ \
                                            --junitxml=/tmp/reports/junit.xml \
                                            --cov=src \
                                            --cov-fail-under=${env.COVERAGE_THRESHOLD} \
                                            --cov-report=xml:/tmp/reports/coverage.xml \
                                            --cov-report=term \
                                            -m 'not integration' \
                                            -v
                                    "
                            """
                        }
                    }

                    parallel parallelTests
                }
            }
            post {
                always {
                    // Publish JUnit results for each Lambda.
                    junit allowEmptyResults: true,
                          testResults: "${env.ARTIFACTS_DIR}/**/junit.xml"

                    // Publish coverage reports
                    publishHTML(target: [
                        allowMissing: true,
                        reportDir: "${env.ARTIFACTS_DIR}",
                        reportFiles: '**/coverage.xml',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }

        // ── 5. Integration Tests (Main Branch Only) ───────────────────────────
        stage('Integration Tests') {
            when {
                branch 'main'
            }
            steps {
                script {
                    def parallelIntegration = [:]

                    env.LAMBDAS.split(' ').each { lambda ->
                        parallelIntegration[lambda] = {
                            echo "Running integration tests: ${lambda}"
                            sh """
                                docker run --rm --entrypoint "" \
                                    -e AWS_DEFAULT_REGION=\${AWS_DEFAULT_REGION:-us-west-2} \
                                    -e AWS_ACCESS_KEY_ID=\${AWS_ACCESS_KEY_ID} \
                                    -e AWS_SECRET_ACCESS_KEY=\${AWS_SECRET_ACCESS_KEY} \
                                    lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                    bash -c "
                                        cd \${LAMBDA_TASK_ROOT}
                                        pytest tests/ \
                                            -m integration \
                                            --maxfail=1 \
                                            -v
                                    "
                            """
                        }
                    }

                    parallel parallelIntegration
                }
            }
        }

        // ── 6. Package ZIP (Inside Docker for Reproducibility) ────────────────
        // Creates a deployment ZIP per Lambda: src/ + shared layer + deps.
        // This is what gets deployed to AWS Lambda (not the Docker image).
        // FIXED: Now runs inside Docker for full reproducibility.
        stage('Package ZIP') {
            steps {
                script {
                    def parallelPackage = [:]

                    env.LAMBDAS.split(' ').each { lambda ->
                        parallelPackage[lambda] = {
                            echo "Packaging ZIP for: ${lambda}"
                            sh """
                                mkdir -p ${env.ARTIFACTS_DIR}/${lambda}

                                docker run --rm --entrypoint "" \
                                    -v \$(pwd)/${env.ARTIFACTS_DIR}/${lambda}:/tmp/artifacts \
                                    lambda-${lambda}-ci:${env.BUILD_NUMBER} \
                                    bash -c "
                                        # Create build directory
                                        mkdir -p /tmp/lambda-build

                                        # Copy application source
                                        cp -r \${LAMBDA_TASK_ROOT}/src /tmp/lambda-build/

                                        # Copy shared layer (mirrors the AWS Lambda Layer structure)
                                        if [ -d /opt/python ]; then
                                            cp -r /opt/python/* /tmp/lambda-build/
                                        fi

                                        # Copy any additional config files
                                        if [ -f \${LAMBDA_TASK_ROOT}/incident_config.json ]; then
                                            cp \${LAMBDA_TASK_ROOT}/incident_config.json /tmp/lambda-build/
                                        fi

                                        # Create the ZIP artifact (deps already in image from Dockerfile)
                                        cd /tmp/lambda-build
                                        zip -r /tmp/artifacts/${lambda}-${env.BUILD_NUMBER}.zip . \
                                            -x '*.pyc' \
                                            -x '*/__pycache__/*' \
                                            -x '*/test_*.py' \
                                            -x '*/tests/*' \
                                            -x '*/.pytest_cache/*' \
                                            -x '*/.git/*'

                                        # Show ZIP contents for verification
                                        echo '=== ZIP Contents ==='
                                        unzip -l /tmp/artifacts/${lambda}-${env.BUILD_NUMBER}.zip | head -30
                                    "
                            """
                        }
                    }

                    parallel parallelPackage
                }
            }
        }

        // ── 7. Archive Artifacts ──────────────────────────────────────────────
        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: "${env.ARTIFACTS_DIR}/**/*.zip",
                                 fingerprint: true,
                                 allowEmptyArchive: false
                echo '✅ ZIP packages archived. Ready for deployment via CDK.'
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
            echo "📦 Deployment artifacts:"
            sh "ls -lh ${env.ARTIFACTS_DIR}/*/*.zip 2>/dev/null || true"
        }
        failure {
            echo "❌ Pipeline FAILED — check stage logs above."
        }
    }
}
