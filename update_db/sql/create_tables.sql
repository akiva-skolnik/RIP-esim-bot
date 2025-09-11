USE collections;

CREATE TABLE IF NOT EXISTS mm_history (
    server VARCHAR(50),
    country_id VARCHAR(10),
    date DATE,
    price DECIMAL(10,4),
    count INT,
    PRIMARY KEY (server, country_id, date, price)
);

CREATE TABLE IF NOT EXISTS prices_history (
    product VARCHAR(50),
    server VARCHAR(50),
    date DATE,
    price DECIMAL(10,4),
    count INT,
    PRIMARY KEY (server, product, date, price)
);

-- Create indexes for better query performance
CREATE INDEX idx_mm_history_server ON mm_history(server);
CREATE INDEX idx_mm_history_date ON mm_history(date);

CREATE INDEX idx_prices_history_server ON prices_history(server);
CREATE INDEX idx_prices_history_date ON prices_history(date);
