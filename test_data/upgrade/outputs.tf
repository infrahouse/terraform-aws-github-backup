output "s3_bucket_name" {
  value = module.main.s3_bucket_name
}

output "replica_bucket_name" {
  value = module.main.replica_bucket_name
}

output "ecs_cluster_name" {
  value = module.main.ecs_cluster_name
}
