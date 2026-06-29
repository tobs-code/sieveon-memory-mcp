#!/bin/bash
# Start SurrealDB for Strata
# This script starts a SurrealDB instance configured for Strata

echo "Starting SurrealDB for Strata..."
echo "=================================="

# Check if surreal command is available
if ! command -v surreal &> /dev/null; then
    echo "Error: surreal command not found"
    echo "Please install SurrealDB first:"
    echo "  - Download from https://github.com/surrealdb/surrealdb"
    echo "  - Or use: cargo install surrealdb"
    exit 1
fi

# Use environment variables or defaults
SURREALDB_USER=${SURREALDB_USER:-root}
SURREALDB_PASS=${SURREALDB_PASS:-root}
SURREALDB_NS=${SURREALDB_NS:-agent_memory}
SURREALDB_DB=${SURREALDB_DB:-agent_memory}

echo "Configuration:"
echo "  User: $SURREALDB_USER"
echo "  Namespace: $SURREALDB_NS"
echo "  Database: $SURREALDB_DB"
echo ""

# Start SurrealDB
echo "Starting SurrealDB server..."
surreal start \
    --user "$SURREALDB_USER" \
    --pass "$SURREALDB_PASS" \
    --bind 127.0.0.1:8000 \
    --log trace

echo ""
echo "=================================="
echo "SurrealDB for Strata stopped."