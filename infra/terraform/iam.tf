# Least-privilege policies. Attach them to the role/user of the uploader (CI or the app)
# and of the query runner (CI data-validation job). Neither can delete data or touch other
# buckets, workgroups or databases.

data "aws_iam_policy_document" "uploader" {
  statement {
    sid       = "PutLogObjectsOnly"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/logs/*"]
  }
  statement {
    sid       = "HeadForIdempotentUpload"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.logs.arn}/logs/*"]
  }
  statement {
    sid       = "EncryptWithLogsKey"
    actions   = ["kms:GenerateDataKey", "kms:Encrypt"]
    resources = [aws_kms_key.logs.arn]
  }
}

resource "aws_iam_policy" "uploader" {
  name        = "${var.name_prefix}-log-uploader"
  description = "Write-only access to s3://<logs>/logs/ for the interaction-log uploader"
  policy      = data.aws_iam_policy_document.uploader.json
}

data "aws_iam_policy_document" "query_runner" {
  statement {
    sid = "RunQueriesInOneWorkgroup"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup",
    ]
    resources = [aws_athena_workgroup.rqg.arn]
  }
  statement {
    sid     = "ReadCatalogForOneTable"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"]
    resources = [
      "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:database/${aws_glue_catalog_database.logs.name}",
      "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.logs.name}/${aws_glue_catalog_table.interactions.name}",
    ]
  }
  statement {
    sid       = "ReadLogs"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.logs.arn}/logs/*"]
  }
  statement {
    sid       = "ListLogsPrefix"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.logs.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["logs/*"]
    }
  }
  statement {
    sid       = "WriteAndReadResults"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:AbortMultipartUpload"]
    resources = [aws_s3_bucket.results.arn, "${aws_s3_bucket.results.arn}/results/*"]
  }
  statement {
    sid       = "UseLogsKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.logs.arn]
  }
}

resource "aws_iam_policy" "query_runner" {
  name        = "${var.name_prefix}-athena-query-runner"
  description = "Run Athena queries against the interactions table in one workgroup"
  policy      = data.aws_iam_policy_document.query_runner.json
}
