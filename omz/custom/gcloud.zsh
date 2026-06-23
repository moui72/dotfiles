# The next line updates PATH for the Google Cloud SDK.
_gcloud_sdk="${CLOUDSDK_ROOT_DIR:-$HOME/Downloads/google-cloud-sdk}"
if [ -f "$_gcloud_sdk/path.zsh.inc" ]; then . "$_gcloud_sdk/path.zsh.inc"; fi

# The next line enables shell command completion for gcloud.
if [ -f "$_gcloud_sdk/completion.zsh.inc" ]; then . "$_gcloud_sdk/completion.zsh.inc"; fi
unset _gcloud_sdk
