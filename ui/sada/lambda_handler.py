"""AWS Lambda entry point (deploy/deploy.sh): the Django app behind a Lambda function URL, via apig-wsgi."""
from apig_wsgi import make_lambda_handler

from config.wsgi import application

handler = make_lambda_handler(application)
