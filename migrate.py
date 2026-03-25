from db import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as connection:
        print("Checking for user_email column...")
    
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='contract_analysis' AND column_name='user_email';
        """))
        exists = result.fetchone()
        
        if not exists:
            print("Adding user_email column...")
            connection.execute(text("ALTER TABLE contract_analysis ADD COLUMN user_email VARCHAR;"))
            connection.execute(text("CREATE INDEX ix_contract_analysis_user_email ON contract_analysis (user_email);"))
            connection.commit()
            print("Column added successfully.")
        else:
            print("Column already exists.")

        print("Checking if unique constraint on file_hash exists...")
      
        try:
            connection.execute(text("ALTER TABLE contract_analysis DROP CONSTRAINT IF EXISTS contract_analysis_file_hash_key;"))
            connection.commit()
            print("Unique constraint dropped (if it existed).")
        except Exception as e:
            print(f"Note: Could not drop constraint: {e}")

if __name__ == "__main__":
    migrate()
