import logging

from infrahouse_core.logging import setup_logging

# "303467602807" is our test account
TEST_ACCOUNT = "303467602807"
DEFAULT_PROGRESS_INTERVAL = 10
TASK_RUN_TIMEOUT = 600  # seconds to wait for ECS task

# InfraHouse GitHub Backup App (installed on the infrahouse org)
GH_APP_ID = "1016509"
GH_APP_INSTALLATION_ID = "55611573"
GH_APP_PEM_SECRET_NAME = "github-backup-test-pem"
GH_APP_PEM_SECRET_REGION = "us-west-1"

LOG = logging.getLogger(__name__)
TERRAFORM_ROOT_DIR = "test_data"

setup_logging(LOG, debug=True)
