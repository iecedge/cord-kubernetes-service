export IMAGE_TAG=$(cat VERSION)
export DOCKER_CLI_EXPERIMENTAL=enabled

docker manifest create --amend cachengo/kubernetes-synchronizer:$IMAGE_TAG cachengo/kubernetes-synchronizer-x86_64:$IMAGE_TAG cachengo/kubernetes-synchronizer-aarch64:$IMAGE_TAG
docker manifest push cachengo/kubernetes-synchronizer:$IMAGE_TAG
