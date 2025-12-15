"""
Script to convert US_Accidents_March23.csv to a SQLite database.
This preprocesses the data for efficient MCP server queries.

Run this script once before starting the MCP server.
"""

import csv
import sqlite3
import os
from datetime import datetime
import sys

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "US_Accidents_March23.csv")
DB_PATH = os.path.join(SCRIPT_DIR, "accidents.db")


def parse_datetime(dt_string: str) -> tuple:
    """Parse datetime string and extract components."""
    try:
        dt = datetime.strptime(dt_string[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.hour, dt.weekday()
    except (ValueError, TypeError):
        return None, None, None


def parse_float(value: str) -> float | None:
    """Safely parse float value."""
    try:
        return float(value) if value and value.strip() else None
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    """Safely parse int value."""
    try:
        return int(value) if value and value.strip() else None
    except ValueError:
        return None


def parse_bool(value: str) -> int:
    """Parse boolean string to 0/1."""
    return 1 if value.lower() == 'true' else 0


def calculate_duration(start_str: str, end_str: str) -> float | None:
    """Calculate duration in minutes between start and end times."""
    try:
        start = datetime.strptime(start_str[:19], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(end_str[:19], "%Y-%m-%d %H:%M:%S")
        duration = (end - start).total_seconds() / 60
        # Filter out unreasonable durations (negative or > 48 hours)
        if 0 < duration < 48 * 60:
            return duration
        return None
    except (ValueError, TypeError):
        return None


def create_database():
    """Create the SQLite database with optimized schema."""
    print(f"Creating database at {DB_PATH}...")
    
    # Remove existing database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create main accidents table with relevant columns
    cursor.execute("""
        CREATE TABLE accidents (
            ID TEXT PRIMARY KEY,
            Source TEXT,
            Severity INTEGER,
            Start_Time TEXT,
            End_Time TEXT,
            Start_Lat REAL,
            Start_Lng REAL,
            Distance_mi REAL,
            Description TEXT,
            Street TEXT,
            City TEXT,
            County TEXT,
            State TEXT,
            Zipcode TEXT,
            Timezone TEXT,
            Temperature_F REAL,
            Humidity_pct REAL,
            Pressure_in REAL,
            Visibility_mi REAL,
            Wind_Direction TEXT,
            Wind_Speed_mph REAL,
            Precipitation_in REAL,
            Weather_Condition TEXT,
            Amenity INTEGER,
            Bump INTEGER,
            Crossing INTEGER,
            Give_Way INTEGER,
            Junction INTEGER,
            No_Exit INTEGER,
            Railway INTEGER,
            Roundabout INTEGER,
            Station INTEGER,
            Stop INTEGER,
            Traffic_Calming INTEGER,
            Traffic_Signal INTEGER,
            Turning_Loop INTEGER,
            Sunrise_Sunset TEXT,
            -- Computed columns for faster queries
            hour_of_day INTEGER,
            day_of_week INTEGER,
            Duration_minutes REAL
        )
    """)
    
    conn.commit()
    return conn


def load_data(conn):
    """Load CSV data into SQLite database."""
    cursor = conn.cursor()
    
    print(f"Loading data from {CSV_PATH}...")
    print("This may take several minutes")
    
    # Column indices from CSV header
    # ID,Source,Severity,Start_Time,End_Time,Start_Lat,Start_Lng,End_Lat,End_Lng,
    # Distance(mi),Description,Street,City,County,State,Zipcode,Country,Timezone,
    # Airport_Code,Weather_Timestamp,Temperature(F),Wind_Chill(F),Humidity(%),
    # Pressure(in),Visibility(mi),Wind_Direction,Wind_Speed(mph),Precipitation(in),
    # Weather_Condition,Amenity,Bump,Crossing,Give_Way,Junction,No_Exit,Railway,
    # Roundabout,Station,Stop,Traffic_Calming,Traffic_Signal,Turning_Loop,
    # Sunrise_Sunset,Civil_Twilight,Nautical_Twilight,Astronomical_Twilight
    
    batch_size = 50000
    batch = []
    total_rows = 0
    skipped_rows = 0
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        
        for row in reader:
            try:
                if len(row) != len(header):
                    skipped_rows += 1
                    continue
                
                # Parse datetime and extract hour/day
                start_time, hour_of_day, day_of_week = parse_datetime(row[3])
                if start_time is None:
                    skipped_rows += 1
                    continue
                
                # Calculate duration
                duration = calculate_duration(row[3], row[4])
                
                record = (
                    row[0],                           # ID
                    row[1],                           # Source
                    parse_int(row[2]),                # Severity
                    start_time,                       # Start_Time
                    row[4][:19] if row[4] else None,  # End_Time
                    parse_float(row[5]),              # Start_Lat
                    parse_float(row[6]),              # Start_Lng
                    parse_float(row[9]),              # Distance_mi
                    row[10][:500] if row[10] else None,  # Description (truncated)
                    row[11],                          # Street
                    row[12],                          # City
                    row[13],                          # County
                    row[14],                          # State
                    row[15],                          # Zipcode
                    row[17],                          # Timezone
                    parse_float(row[20]),             # Temperature_F
                    parse_float(row[22]),             # Humidity_pct
                    parse_float(row[23]),             # Pressure_in
                    parse_float(row[24]),             # Visibility_mi
                    row[25],                          # Wind_Direction
                    parse_float(row[26]),             # Wind_Speed_mph
                    parse_float(row[27]),             # Precipitation_in
                    row[28],                          # Weather_Condition
                    parse_bool(row[29]),              # Amenity
                    parse_bool(row[30]),              # Bump
                    parse_bool(row[31]),              # Crossing
                    parse_bool(row[32]),              # Give_Way
                    parse_bool(row[33]),              # Junction
                    parse_bool(row[34]),              # No_Exit
                    parse_bool(row[35]),              # Railway
                    parse_bool(row[36]),              # Roundabout
                    parse_bool(row[37]),              # Station
                    parse_bool(row[38]),              # Stop
                    parse_bool(row[39]),              # Traffic_Calming
                    parse_bool(row[40]),              # Traffic_Signal
                    parse_bool(row[41]),              # Turning_Loop
                    row[42],                          # Sunrise_Sunset
                    hour_of_day,                      # hour_of_day (computed)
                    day_of_week,                      # day_of_week (computed)
                    duration                          # Duration_minutes (computed)
                )
                
                batch.append(record)
                total_rows += 1
                
                if len(batch) >= batch_size:
                    cursor.executemany("""
                        INSERT INTO accidents VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                    """, batch)
                    conn.commit()
                    print(f"  Processed {total_rows:,} records...")
                    batch = []
                    
            except Exception as e:
                skipped_rows += 1
                if skipped_rows < 10:
                    print(f"  Warning: Skipping row due to error: {e}")
    
    # Insert remaining batch
    if batch:
        cursor.executemany("""
            INSERT INTO accidents VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, batch)
        conn.commit()
    
    print(f"Loaded {total_rows:,} records ({skipped_rows:,} skipped)")
    return total_rows


def create_indexes(conn):
    """Create indexes for faster queries."""
    cursor = conn.cursor()
    print("Creating indexes for faster queries...")
    
    indexes = [
        ("idx_state", "State"),
        ("idx_city", "City"),
        ("idx_severity", "Severity"),
        ("idx_start_time", "Start_Time"),
        ("idx_hour_day", "hour_of_day, day_of_week"),
        ("idx_location", "Start_Lat, Start_Lng"),
        ("idx_weather", "Weather_Condition"),
        ("idx_state_city", "State, City"),
    ]
    
    for idx_name, columns in indexes:
        print(f"  Creating index {idx_name}...")
        cursor.execute(f"CREATE INDEX {idx_name} ON accidents ({columns})")
    
    conn.commit()
    print("Indexes created successfully!")


def verify_database(conn):
    """Verify database integrity and print summary."""
    cursor = conn.cursor()
    
    print("\n" + "="*50)
    print("DATABASE VERIFICATION")
    print("="*50)
    
    # Total records
    cursor.execute("SELECT COUNT(*) FROM accidents")
    total = cursor.fetchone()[0]
    print(f"Total records: {total:,}")
    #Should be about 3 million records
    
    # Records by state (top 5)
    cursor.execute("""
        SELECT State, COUNT(*) as cnt 
        FROM accidents 
        GROUP BY State 
        ORDER BY cnt DESC 
        LIMIT 5
    """)
    print("\nTop 5 states by accidents:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    
    # Severity distribution
    cursor.execute("""
        SELECT Severity, COUNT(*) as cnt 
        FROM accidents 
        GROUP BY Severity 
        ORDER BY Severity
    """)
    print("\nSeverity distribution:")
    for row in cursor.fetchall():
        print(f"  Level {row[0]}: {row[1]:,}")
    
    # Date range
    cursor.execute("SELECT MIN(Start_Time), MAX(Start_Time) FROM accidents")
    date_range = cursor.fetchone()
    print(f"\nDate range: {date_range[0]} to {date_range[1]}")
    
    # Database file size
    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"\nDatabase file size: {db_size:.1f} MB")
    
    print("="*50)


def main():
    """Main function to build the database."""
    print("US Accidents Database Builder")
    print("="*50)
    
    # Check if CSV exists
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV file not found at {CSV_PATH}")
        print("Please download the dataset from Kaggle and place it in the project directory.")
        sys.exit(1)
    
    # Create database
    conn = create_database()
    
    try:
        # Load data
        total_records = load_data(conn)
        
        if total_records == 0:
            print("ERROR: No records were loaded!")
            sys.exit(1)
        
        # Create indexes
        create_indexes(conn)
        
        # Verify
        verify_database(conn)
        
        print("\nDatabase created successfully!")
        print(f"Database location: {DB_PATH}")
        print("\nYou can now start the MCP server with:")
        print("  python -m mcp_server.server")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
