import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2 import sql

# PostgreSQL Database Settings
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'jadetunnel_base',
    'user': 'cbu_user',
    'password': 'Admin1374'
}

def test_connection():
    """Test database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            dbname='postgres'
        )
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
        print("  2. Is the username and password correct?")
        print("  3. Is the port (5432) correct?")
        return False

def create_database():
    """Create database if it doesn't exist"""
    try:
        # Connect to default postgres database as postgres user
        conn = psycopg2.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user='postgres',
            password='Admin1374'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", 
            (DB_CONFIG['database'],)
        )
        exists = cursor.fetchone()
        
        if not exists:
            # Create database
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(DB_CONFIG['database'])
                )
            )
            print(f"✅ Database '{DB_CONFIG['database']}' created successfully!")
        else:
            print(f"ℹ️ Database '{DB_CONFIG['database']}' already exists.")
        
        # Grant privileges to cbu_user
        cursor.execute(
            sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO cbu_user").format(
                sql.Identifier(DB_CONFIG['database'])
            )
        )
        print("✅ Privileges granted to cbu_user")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        return False

def create_tables():
    """Create all necessary tables with proper permissions"""
    try:
        # Connect to the target database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("\n📊 Creating tables...")
        
        # Set schema search path
        cursor.execute("SET search_path TO public;")
        
        # Create users table (no foreign key yet)
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
        
        # Create subscriptions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                protocol VARCHAR(50) NOT NULL,
                duration_days INTEGER NOT NULL,
                config_data TEXT NOT NULL,
                start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_date TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'active'
            )
        """)
        print("✅ Subscriptions table created/verified")
        
        # Create transactions table
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
        
        # Create invite codes table
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
        
        # Now add foreign key constraints (without IF NOT EXISTS)
        try:
            cursor.execute("""
                ALTER TABLE subscriptions 
                ADD CONSTRAINT fk_subscriptions_user 
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            """)
            print("✅ Foreign key added: subscriptions -> users")
        except psycopg2.errors.DuplicateObject:
            print("ℹ️ Foreign key fk_subscriptions_user already exists")
        except Exception as e:
            print(f"⚠️ Could not add constraint fk_subscriptions_user: {e}")
        
        try:
            cursor.execute("""
                ALTER TABLE transactions 
                ADD CONSTRAINT fk_transactions_user 
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            """)
            print("✅ Foreign key added: transactions -> users")
        except psycopg2.errors.DuplicateObject:
            print("ℹ️ Foreign key fk_transactions_user already exists")
        except Exception as e:
            print(f"⚠️ Could not add constraint fk_transactions_user: {e}")
        
        try:
            cursor.execute("""
                ALTER TABLE invite_codes 
                ADD CONSTRAINT fk_invite_codes_user 
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            """)
            print("✅ Foreign key added: invite_codes -> users")
        except psycopg2.errors.DuplicateObject:
            print("ℹ️ Foreign key fk_invite_codes_user already exists")
        except Exception as e:
            print(f"⚠️ Could not add constraint fk_invite_codes_user: {e}")
        
        try:
            cursor.execute("""
                ALTER TABLE users 
                ADD CONSTRAINT fk_users_referred 
                FOREIGN KEY (referred_by) REFERENCES users(user_id) ON DELETE SET NULL
            """)
            print("✅ Foreign key added: users -> users (referred_by)")
        except psycopg2.errors.DuplicateObject:
            print("ℹ️ Foreign key fk_users_referred already exists")
        except Exception as e:
            print(f"⚠️ Could not add constraint fk_users_referred: {e}")
        
        # Create indexes
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invite_codes_user_id ON invite_codes(user_id)")
            print("✅ Indexes created/verified")
        except Exception as e:
            print(f"⚠️ Could not create indexes: {e}")
        
        # Grant privileges on all tables
        try:
            cursor.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cbu_user")
            cursor.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cbu_user")
            cursor.execute("GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO cbu_user")
            print("✅ Privileges granted on all objects")
        except Exception as e:
            print(f"⚠️ Could not grant privileges: {e}")
        
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
        
        # Drop tables in correct order to handle foreign keys
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
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = cursor.fetchall()
        
        if tables:
            print("\n📋 Tables in database:")
            print("-" * 30)
            for table in tables:
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
                    count = cursor.fetchone()[0]
                    print(f"  • {table[0]} ({count} rows)")
                except:
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

def fix_permissions():
    """Fix permissions for the database"""
    try:
        # Connect as postgres user
        conn = psycopg2.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user='postgres',
            password='Admin1374',
            dbname='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Grant schema permissions
        cursor.execute('GRANT ALL ON SCHEMA public TO cbu_user')
        cursor.execute(f'GRANT ALL PRIVILEGES ON DATABASE {DB_CONFIG["database"]} TO cbu_user')
        
        # Connect to the target database
        conn2 = psycopg2.connect(**DB_CONFIG)
        cursor2 = conn2.cursor()
        
        # Grant permissions on all tables
        cursor2.execute("""
            SELECT 'GRANT ALL PRIVILEGES ON ' || tablename || ' TO cbu_user;'
            FROM pg_tables
            WHERE schemaname = 'public'
        """)
        grant_statements = cursor2.fetchall()
        
        for stmt in grant_statements:
            try:
                cursor2.execute(stmt[0])
            except:
                pass
        
        conn2.commit()
        cursor2.close()
        conn2.close()
        
        cursor.close()
        conn.close()
        print("✅ Permissions fixed successfully!")
        return True
    except Exception as e:
        print(f"❌ Error fixing permissions: {e}")
        return False

def main():
    print("🚀 Setting up PostgreSQL database for VPN Bot...")
    print("=" * 50)
    
    # First, fix permissions
    print("\n🔧 Fixing database permissions...")
    if not fix_permissions():
        print("⚠️ Could not fix permissions automatically.")
        print("Please run these commands in psql as postgres user:")
        print(f"  GRANT ALL ON SCHEMA public TO cbu_user;")
        print(f"  GRANT ALL PRIVILEGES ON DATABASE {DB_CONFIG['database']} TO cbu_user;")
        print(f"  \\c {DB_CONFIG['database']}")
        print(f"  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cbu_user;")
        print(f"  GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cbu_user;")
    
    # Test connection with cbu_user
    print("\n🔌 Testing connection with cbu_user...")
    if not test_connection():
        print("\n❌ Cannot connect with cbu_user.")
        exit(1)
    
    # Create database if not exists
    if not create_database():
        print("❌ Failed to create database.")
        exit(1)
    
    # Create tables
    if not create_tables():
        print("❌ Failed to create tables.")
        exit(1)
    
    # Show tables
    show_tables()
    
    print("\n" + "=" * 50)
    print("✅ Database setup completed successfully!")
    print(f"📊 Database: {DB_CONFIG['database']}")
    print(f"👤 User: {DB_CONFIG['user']}")
    print(f"🌐 Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    
    # Ask user if they want to verify tables
    verify = input("\n🔍 Do you want to verify table structures? (y/n): ")
    if verify.lower() == 'y':
        verify_tables()

if __name__ == "__main__":
    main()
