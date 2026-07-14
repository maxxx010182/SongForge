#!/bin/bash
source /root/SongForge/venv/bin/activate
export GETPLATINUM_API_KEY="krCE5bhh2VhX4BmFI5fftOIChveMaPZk6abhl4izx3t7ctL21dUXEMjV54oF32eJ"
export GETPLATINUM_SECRET="krCE5bhh2VhX4BmFI5fftOIChveMaPZk6abhl4izx3t7ctL21dUXEMjV54oF32eJ"
export $(grep -v '^#' /root/SongForge/.env | xargs)
uvicorn app:app --host 0.0.0.0 --port 8000
