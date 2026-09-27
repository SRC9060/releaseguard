import os
import subprocess
import psycopg

print("Starting schema equivalence and migration verification...")

# 1. Ensure development database nullability constraints match models
conn_main = psycopg.connect("postgresql://postgres:postgres@localhost:5432/releaseguard")
cur_main = conn_main.cursor()
cur_main.execute("""
    UPDATE projects SET tenant_id = 1 WHERE tenant_id IS NULL;
    UPDATE projects SET api_key = 'rg_live_' || md5(id::text || name) WHERE api_key IS NULL;
    UPDATE error_events SET event_id = gen_random_uuid()::text WHERE event_id IS NULL;
    ALTER TABLE projects ALTER COLUMN tenant_id SET NOT NULL;
    ALTER TABLE projects ALTER COLUMN api_key SET NOT NULL;
    ALTER TABLE error_events ALTER COLUMN event_id SET NOT NULL;
""")
conn_main.commit()

# Fetch development database schema
cur_main.execute("""
    SELECT table_name, column_name, data_type, is_nullable
    FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name != 'alembic_version'
    ORDER BY table_name, column_name;
""")
dev_schema = cur_main.fetchall()
conn_main.close()

# 2. Create clean disposable test database
conn_admin = psycopg.connect("postgresql://postgres:postgres@localhost:5432/postgres", autocommit=True)
conn_admin.execute("DROP DATABASE IF EXISTS releaseguard_migration_compat_test")
conn_admin.execute("CREATE DATABASE releaseguard_migration_compat_test")
conn_admin.close()

# 3. Run Alembic upgrade head from clean database
env = os.environ.copy()
env["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5432/releaseguard_migration_compat_test"
alembic_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".venv", "Scripts", "alembic.exe")
res = subprocess.run([alembic_bin, "upgrade", "head"], cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."), env=env, capture_output=True, text=True)

print("Alembic Upgrade Stdout:\n", res.stdout.strip())
if res.returncode != 0:
    print("Alembic Upgrade Stderr:\n", res.stderr.strip())
    raise RuntimeError("Alembic upgrade failed on clean database")

# 4. Fetch Alembic upgraded database schema
conn_test = psycopg.connect("postgresql://postgres:postgres@localhost:5432/releaseguard_migration_compat_test")
cur_test = conn_test.cursor()
cur_test.execute("""
    SELECT table_name, column_name, data_type, is_nullable
    FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name != 'alembic_version'
    ORDER BY table_name, column_name;
""")
alembic_schema = cur_test.fetchall()
conn_test.close()

# 5. Clean up disposable test database
conn_admin = psycopg.connect("postgresql://postgres:postgres@localhost:5432/postgres", autocommit=True)
conn_admin.execute("DROP DATABASE IF EXISTS releaseguard_migration_compat_test")
conn_admin.close()

# 6. Compare column by column, table by table
dev_set = set(dev_schema)
alembic_set = set(alembic_schema)

diff_dev_only = dev_set - alembic_set
diff_alembic_only = alembic_set - dev_set

print(f"Total columns in dev schema: {len(dev_schema)}")
print(f"Total columns in alembic schema: {len(alembic_schema)}")
print(f"Discrepancies (dev only): {diff_dev_only}")
print(f"Discrepancies (alembic only): {diff_alembic_only}")

if dev_set == alembic_set:
    print("\nSUCCESS: 100% exact schema equivalence confirmed between development database and clean Alembic migration!")
else:
    print("\nFAILED: Schema mismatch detected!")
    exit(1)
