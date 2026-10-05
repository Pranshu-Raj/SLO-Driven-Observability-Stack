output "public_ip" {
  value = oci_core_instance.k3s.public_ip
}

output "kubectl_tunnel" {
  value = "ssh -N -L 6443:127.0.0.1:6443 ubuntu@${oci_core_instance.k3s.public_ip}"
}
