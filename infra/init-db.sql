-- 为每个服务创建独立 database
CREATE DATABASE nekocafe_reservation;
CREATE DATABASE nekocafe_member;

-- ========== 预约库 ==========
\c nekocafe_reservation;

CREATE TABLE IF NOT EXISTS dining_table (
    id              SERIAL PRIMARY KEY,
    store_id        INTEGER     NOT NULL,
    table_number    VARCHAR(10) NOT NULL,
    capacity        INTEGER     NOT NULL,
    zone            VARCHAR(32),
    status          VARCHAR(20) NOT NULL DEFAULT 'IDLE'
);
CREATE INDEX idx_table_store ON dining_table(store_id);

CREATE TABLE IF NOT EXISTS reservation (
    id              SERIAL PRIMARY KEY,
    member_id       INTEGER     NOT NULL,
    store_id        INTEGER     NOT NULL,
    table_id        INTEGER     NOT NULL,
    reservation_date DATE       NOT NULL,
    start_time      TIME        NOT NULL,
    end_time        TIME        NOT NULL,
    guest_count     INTEGER     NOT NULL,
    cat_preference  VARCHAR(128),
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    deposit_amount  DECIMAL(10,2),
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    cancel_reason   VARCHAR(256)
);
CREATE INDEX idx_rsv_store_date ON reservation(store_id, reservation_date);
CREATE INDEX idx_rsv_member     ON reservation(member_id);
CREATE INDEX idx_rsv_status     ON reservation(status);

INSERT INTO dining_table (store_id, table_number, capacity, zone) VALUES
(1, 'A1', 4, '撸猫区'),
(1, 'A2', 2, '撸猫区'),
(1, 'B1', 6, '主题包间'),
(1, 'B2', 8, '主题包间'),
(1, 'C1', 4, '窗边区');

-- ========== 会员库 ==========
\c nekocafe_member;

CREATE TABLE IF NOT EXISTS member (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(64)  NOT NULL,
    phone           VARCHAR(20)  UNIQUE NOT NULL,
    email           VARCHAR(128),
    avatar          VARCHAR(256),
    level           VARCHAR(20)  NOT NULL DEFAULT 'NORMAL',
    points          INTEGER      NOT NULL DEFAULT 0,
    total_spent     DECIMAL(12,2) NOT NULL DEFAULT 0,
    preferences     JSONB,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_member_phone ON member(phone);
CREATE INDEX idx_member_level ON member(level);
