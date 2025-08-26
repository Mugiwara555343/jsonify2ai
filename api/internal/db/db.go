package db

import (
	"database/sql"
	_ "github.com/lib/pq"
)

// Open creates a new database connection using the provided DSN
func Open(dsn string) (*sql.DB, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	
	// Test the connection
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	
	return db, nil
}
