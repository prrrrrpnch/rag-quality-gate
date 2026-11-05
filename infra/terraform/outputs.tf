output "logs_bucket" {
  value = aws_s3_bucket.logs.bucket
}

output "results_bucket" {
  value = aws_s3_bucket.results.bucket
}

output "athena_workgroup" {
  value = aws_athena_workgroup.rqg.name
}

output "glue_database" {
  value = aws_glue_catalog_database.logs.name
}

output "uploader_policy_arn" {
  value = aws_iam_policy.uploader.arn
}

output "query_runner_policy_arn" {
  value = aws_iam_policy.query_runner.arn
}
