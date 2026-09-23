#!/usr/bin/env bash
# first try graceful stop with SIGTERM
for p in {5001..5007}; do sudo fuser -k -TERM ${p}/udp; done
sleep 1
# then do a forced stop with SIGKILL
for p in {5001..5007}; do sudo fuser -k ${p}/udp; done
