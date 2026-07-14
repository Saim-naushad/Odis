# onnx-runtime

Reserved for a standalone ONNX Runtime Deployment and Service, should forecast inference ever be split out of the `api` process. No manifests are defined yet — forecasting currently runs in-process via `backend/app/infrastructure/inference/`. See [Kubernetes Deployment → Future extensions](../../docs/platform/kubernetes-deployment.md#future-extensions) and [Telemetry Forecasting](../../docs/platform/telemetry-forecasting.md).
