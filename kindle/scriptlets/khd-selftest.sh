#!/bin/sh
# Name: Dashboard: Self-test
# Author: kindle-ha-dash

sh /mnt/us/extensions/kindle-ha-dash/bin/selftest.sh > /mnt/us/kindle-ha-dash-selftest.txt 2>&1
echo "Self-test written to /mnt/us/kindle-ha-dash-selftest.txt"
