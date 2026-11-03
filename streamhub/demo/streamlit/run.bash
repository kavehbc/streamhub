#!/usr/bin/env bash

export APP_FILE=main.py

# Launch StreamLit
streamlit run $APP_FILE $@
# Note: ending line per $@ allows streamhub to pass down the settings to use like port number, etc.
