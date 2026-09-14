import asyncio
import sys
from datetime import datetime, timezone
import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.models import Base, CollectorModel


async def test_connection():
    print("=" * 60)
    print("PENGUJIAN KONEKSI POSTGRESQL: SignalScanner")
    print("=" * 60)

    host = "localhost"
    port = 5432
    user = "postgres"
    password = "postgres"
    target_db = "SignalScanner"

    # Step 1: Test Server Connectivity & Credentials
    print(f"\n[1/5] Menguji autentikasi ke server PostgreSQL ({host}:{port})...")
    try:
        conn = await asyncpg.connect(
            host=host, port=port, user=user, password=password, database="postgres"
        )
        pg_version = await conn.fetchval("SELECT version()")
        print(f"  [OK] Koneksi berhasil! Versi PostgreSQL:\n       {pg_version.split(',')[0]}")
    except Exception as e:
        print(f"  [ERROR] Gagal terhubung ke server PostgreSQL: {e}")
        return False

    # Step 2: Check & Create Database
    print(f"\n[2/5] Memeriksa keberadaan database '{target_db}'...")
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target_db
        )
        if not exists:
            print(f"  [INFO] Database '{target_db}' belum ada. Membuat database '{target_db}'...")
            await conn.execute(f'CREATE DATABASE "{target_db}"')
            print(f"  [OK] Database '{target_db}' berhasil dibuat!")
        else:
            print(f"  [OK] Database '{target_db}' sudah tersedia.")
        await conn.close()
    except Exception as e:
        print(f"  [ERROR] Gagal memeriksa/membuat database: {e}")
        await conn.close()
        return False

    # Step 3: Connect to SignalScanner with SQLAlchemy Async Engine
    target_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{target_db}"
    print(f"\n[3/5] Menghubungkan SQLAlchemy async engine ke:\n       {target_url}...")
    try:
        engine = create_async_engine(target_url, echo=False)
        async with engine.begin() as sql_conn:
            # Step 4: Initialize Schema & Create Tables
            print("\n[4/5] Menginisialisasi skema tabel aplikasi...")
            await sql_conn.run_sync(Base.metadata.create_all)
            
            # List created tables
            res = await sql_conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
            )
            tables = [r[0] for r in res.fetchall()]
            print(f"  [OK] Skema berhasil diinisialisasi! ({len(tables)} tabel):")
            for t in tables:
                print(f"       * {t}")

            # Step 5: Test Read & Write Operation
            print("\n[5/5] Menguji operasi asynchronous INSERT & SELECT...")
            test_collector_id = f"test_probe_{int(datetime.now(timezone.utc).timestamp())}"
            insert_stmt = text(
                """
                INSERT INTO collectors (id, name, platform, version, status, capabilities, last_seen, created_at)
                VALUES (:id, :name, :platform, :version, :status, :capabilities, :last_seen, :created_at)
                """
            )
            await sql_conn.execute(
                insert_stmt,
                {
                    "id": test_collector_id,
                    "name": "PostgreSQL Diagnostic Test Probe",
                    "platform": "windows",
                    "version": "1.0.0",
                    "status": "ready",
                    "capabilities": "{}",
                    "last_seen": datetime.now(timezone.utc),
                    "created_at": datetime.now(timezone.utc),
                }
            )

            # Query back
            select_stmt = text("SELECT id, name, status, created_at FROM collectors WHERE id = :id")
            row = (await sql_conn.execute(select_stmt, {"id": test_collector_id})).fetchone()
            print(f"  [OK] Test query berhasil membaca data yang baru di-insert:")
            print(f"       ID: {row[0]} | Nama: {row[1]} | Status: {row[2]}")

            # Clean up test probe
            await sql_conn.execute(text("DELETE FROM collectors WHERE id = :id"), {"id": test_collector_id})

        await engine.dispose()
        print("\n" + "=" * 60)
        print("HASIL: KONEKSI DATABASE POSTGRESQL 100% SUKSES DAN SIAP DIGUNAKAN!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"  [ERROR] Error saat pengujian SQLAlchemy: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
