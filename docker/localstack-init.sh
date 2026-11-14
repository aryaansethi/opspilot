#!/bin/sh
# Runs inside LocalStack when it is ready: create the buckets/queues the app expects.
set -e
awslocal s3 mb s3://opspilot-documents || true
awslocal s3api put-bucket-cors --bucket opspilot-documents --cors-configuration '{"CORSRules":[{"AllowedOrigins":["http://localhost:3000"],"AllowedMethods":["PUT","GET"],"AllowedHeaders":["*"],"MaxAgeSeconds":3000}]}'
awslocal sqs create-queue --queue-name opspilot-ingest-dlq >/dev/null
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/opspilot-ingest-dlq --attribute-names QueueArn --query Attributes.QueueArn --output text)
awslocal sqs create-queue --queue-name opspilot-ingest \
  --attributes "{\"VisibilityTimeout\":\"300\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" >/dev/null
echo "opspilot localstack resources ready"
awslocal sqs create-queue --queue-name opspilot-investigate-dlq >/dev/null
INV_DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/opspilot-investigate-dlq --attribute-names QueueArn --query Attributes.QueueArn --output text)
awslocal sqs create-queue --queue-name opspilot-investigate \
  --attributes "{\"VisibilityTimeout\":\"600\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$INV_DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"2\\\"}\"}" >/dev/null
echo "opspilot investigate queue ready"
awslocal sqs create-queue --queue-name opspilot-evaluate --attributes '{"VisibilityTimeout":"7200"}' >/dev/null
echo "opspilot evaluate queue ready"
