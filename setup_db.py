import sys
import psycopg2
from psycopg2 import sql

# ============ خواندن اطلاعات دیتابیس از config.json ============
# توجه امنیتی: پسورد دیتابیس دیگر در این فایل هاردکد نمی‌شود.
# اگر نسخه قبلی این فایل را در گیت‌هاب پابلیک کرده‌اید، حتماً پسورد
# دیتابیس را عوض کنید، چون در تاریخچه commit ها همچنان قابل مشاهده است.
from config import config

DB_CONFIG = config.get_db_config()


def test_connection():
    """Test database connection using the app user from config.json"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        print(f"✅ Connected to PostgreSQL: {version[0][:50]}...")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\n📌 Please check:")
        print("  1. Is PostgreSQL installed and running?")
        print("  2. Are db_host/db_port/db_name/db_user/db_password in config.json correct?")
        print("  3. Has the database/role already been created (e.g. by install.sh)?")
        return False


def create_tables():
    """Create all necessary tables with proper permissions"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("\n📊 Creating tables...")
        cursor.execute("SET search_path TO public;")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                balance BIGINT DEFAULT 30000,
                referred_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Users table created/verified")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                protocol VARCHAR(50) NOT NULL,
                duration_days INTEGER NOT NULL,
                config_data TEXT,
                email VARCHAR(255),
                panel_id VARCHAR(100),
                plan_type VARCHAR(50),
                plan_name VARCHAR(255),
                remaining_volume NUMERIC DEFAULT 0,
                start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_date TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'active'
            )
        """)
        print("✅ Subscriptions table created/verified")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount BIGINT NOT NULL,
                type VARCHAR(50) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Transactions table created/verified")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                code VARCHAR(50) PRIMARY KEY,
                user_id BIGINT NOT NULL,
                uses INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Invite codes table created/verified")

        # Foreign keys (idempotent)
        for constraint_sql, label in [
            ("""ALTER TABLE subscriptions ADD CONSTRAINT fk_subscriptions_user
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE""",
             "subscriptions -> users"),
            ("""ALTER TABLE transactions ADD CONSTRAINT fk_transactions_user
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE""",
             "transactions -> users"),
            ("""ALTER TABLE invite_codes ADD CONSTRAINT fk_invite_codes_user
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE""",
             "invite_codes -> users"),
            ("""ALTER TABLE users ADD CONSTRAINT fk_users_referred
                FOREIGN KEY (referred_by) REFERENCES users(user_id) ON DELETE SET NULL""",
             "users -> users (referred_by)"),
        ]:
            try:
                cursor.execute(constraint_sql)
                print(f"✅ Foreign key added: {label}")
            except psycopg2.errors.DuplicateObject:
                conn.rollback()
                print(f"ℹ️ Foreign key already exists: {label}")
            except Exception as e:
                conn.rollback()
                print(f"⚠️ Could not add constraint ({label}): {e}")

        # Indexes
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invite_codes_user_id ON invite_codes(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)")
            print("✅ Indexes created/verified")
        except Exception as e:
            print(f"⚠️ Could not create indexes: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        print("\n✅ All tables created successfully!")
        return True
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        if 'conn' in locals():
            conn.rollback()
        return False


def drop_all_tables():
    """Drop all tables (use with caution!)"""
    confirm = input("⚠️ Are you sure you want to drop ALL tables? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Operation cancelled.")
        return False

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
        cursor.execute("DROP TABLE IF EXISTS transactions CASCADE")
        cursor.execute("DROP TABLE IF EXISTS invite_codes CASCADE")
        cursor.execute("DROP TABLE IF EXISTS users CASCADE")
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ All tables dropped successfully!")
        return True
    except Exception as e:
        print(f"❌ Error dropping tables: {e}")
        return False


def show_tables():
    """Show all tables in the database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tables = cursor.fetchall()

        if tables:
            print("\n📋 Tables in database:")
            print("-" * 30)
            for table in tables:
                try:
                    cursor.execute(
                        sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table[0]))
                    )
                    count = cursor.fetchone()[0]
                    print(f"  • {table[0]} ({count} rows)")
                except Exception:
                    print(f"  • {table[0]}")
        else:
            print("\n📭 No tables found in database.")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error showing tables: {e}")


def verify_tables():
    """Verify table structures"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        tables = ['users', 'subscriptions', 'transactions', 'invite_codes']
        print("\n🔍 Verifying table structures...")
        print("-" * 40)

        for table in tables:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
            """, (table,))
            columns = cursor.fetchall()

            if columns:
                print(f"\n📊 Table: {table}")
                for col in columns:
                    print(f"  • {col[0]}: {col[1]} (nullable: {col[2]})")
            else:
                print(f"\n⚠️ Table '{table}' not found!")

        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error verifying tables: {e}")
        return False


def main():
    auto_mode = "--auto" in sys.argv

    print("🚀 Setting up PostgreSQL tables for Jade Tunnel Bot...")
    print("=" * 50)
    print(f"📊 Database: {DB_CONFIG['database']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"👤 User: {DB_CONFIG['user']}")
    print("=" * 50)

    print("\n🔌 Testing connection...")
    if not test_connection():
        print("\n❌ Cannot connect to database with credentials from config.json.")
        print("   اگر تازه دیتابیس/کاربر را ساخته‌اید، مطمئن شوید نصب PostgreSQL کامل شده است.")
        sys.exit(1)

    if not create_tables():
        print("❌ Failed to create tables.")
        sys.exit(1)

    show_tables()

    print("\n" + "=" * 50)
    print("✅ Database setup completed successfully!")

    if not auto_mode:
        verify = input("\n🔍 Do you want to verify table structures? (y/n): ")
        if verify.lower() == 'y':
            verify_tables()


if __name__ == "__main__":
    main()
