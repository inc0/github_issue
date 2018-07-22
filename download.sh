if [ ! -f /data/github-issues.zip ]; then
    wget --directory-prefix=/data https://storage.googleapis.com/kubeflow-examples/github-issue-summarization-data/github-issues.zip
    unzip /data/github-issues.zip -d /data
fi
