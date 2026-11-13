#!/usr/bin/env bash

# Command to inject rotating random chaos/errors into the system
# Rotates through: Database Outage, Java NullPointerException, Transaction Rollback, Insurance Rule Rejection, etc.

curl -s -X POST "http://localhost:5001/api/simulate-incident" | python3 -m json.tool
