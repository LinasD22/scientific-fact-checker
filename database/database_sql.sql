DROP TABLE IF EXISTS Teikiama_paslauga;
DROP TABLE IF EXISTS Mokejimas;
DROP TABLE IF EXISTS Uzklausa;
DROP TABLE IF EXISTS Prenumerata;
DROP TABLE IF EXISTS Naudotojas;
DROP TABLE IF EXISTS Statusas;
DROP TABLE IF EXISTS Busena;
DROP TABLE IF EXISTS Svecias;
DROP TABLE IF EXISTS Prisijungimas;


CREATE TABLE Busena
(
    Id   INTEGER     NOT NULL,
    Name VARCHAR(50) NOT NULL,
    PRIMARY KEY (Id)
);

INSERT INTO Busena (Id, Name) VALUES (1, 'Aktyvi');
INSERT INTO Busena (Id, Name) VALUES (2, 'Atsaukta');
INSERT INTO Busena (Id, Name) VALUES (3, 'Sustabdyta');


CREATE TABLE Statusas
(
    Id   INTEGER     NOT NULL,
    Name VARCHAR(50) NOT NULL,
    PRIMARY KEY (Id)
);

INSERT INTO Statusas (Id, Name) VALUES (1, 'Pavyko');
INSERT INTO Statusas (Id, Name) VALUES (2, 'Nepavyko');
INSERT INTO Statusas (Id, Name) VALUES (3, 'Atsaukta');
INSERT INTO Statusas (Id, Name) VALUES (4, 'Laukiama mokejimo');


CREATE TABLE Prisijungimas
(
    El_pastas   VARCHAR(255) NOT NULL,
    Slaptazodis VARCHAR(255) NOT NULL,
    PRIMARY KEY (El_pastas)
);


CREATE TABLE Svecias
(
    Id                INTEGER      NOT NULL AUTO_INCREMENT,
    Ip_adresas        VARCHAR(255) NOT NULL,
    Uzklausu_skaicius INTEGER      NOT NULL DEFAULT 0,
    PRIMARY KEY (Id),
    UNIQUE (Ip_adresas)
);


CREATE TABLE Naudotojas
(
    Id               INTEGER      NOT NULL AUTO_INCREMENT,
    Vardas           VARCHAR(255) NOT NULL,
    Pavarde          VARCHAR(255) NOT NULL,
    El_pastas        VARCHAR(255) NOT NULL,
    fk_Prisijungimas VARCHAR(255) NOT NULL,
    PRIMARY KEY (Id),
    UNIQUE (El_pastas),
    UNIQUE (fk_Prisijungimas),
    CONSTRAINT fk_Naudotojas_Prisijungimas
        FOREIGN KEY (fk_Prisijungimas)
        REFERENCES Prisijungimas (El_pastas)
);

CREATE INDEX idx_Naudotojas_fk_Prisijungimas ON Naudotojas (fk_Prisijungimas);


CREATE TABLE Prenumerata
(
    Id                 INTEGER NOT NULL AUTO_INCREMENT,
    Pradzios_laikas    DATE    NOT NULL,
    Atnaujinimo_laikas DATE    NOT NULL,
    Atliktos_uzklausos INTEGER NOT NULL DEFAULT 0,
    fk_Busena          INTEGER NOT NULL,
    fk_Naudotojas      INTEGER NOT NULL,
    PRIMARY KEY (Id),
    CONSTRAINT fk_Prenumerata_Busena
        FOREIGN KEY (fk_Busena)
        REFERENCES Busena (Id),
    CONSTRAINT fk_Prenumerata_Naudotojas
        FOREIGN KEY (fk_Naudotojas)
        REFERENCES Naudotojas (Id)
);

CREATE INDEX idx_Prenumerata_fk_Busena     ON Prenumerata (fk_Busena);
CREATE INDEX idx_Prenumerata_fk_Naudotojas ON Prenumerata (fk_Naudotojas);


CREATE TABLE Teikiama_paslauga
(
    Id               INTEGER        NOT NULL AUTO_INCREMENT,
    Pavadinimas      VARCHAR(255)   NOT NULL,
    Kaina            DECIMAL(10, 2) NOT NULL,
    Trukme           INTEGER        NOT NULL,
    Uzklausu_limitas INTEGER        NOT NULL,
    fk_Prenumerata   INTEGER        NOT NULL,
    PRIMARY KEY (Id),
    UNIQUE (fk_Prenumerata),
    CONSTRAINT fk_Teikiama_paslauga_Prenumerata
        FOREIGN KEY (fk_Prenumerata)
        REFERENCES Prenumerata (Id)
);

CREATE INDEX idx_Teikiama_paslauga_fk_Prenumerata ON Teikiama_paslauga (fk_Prenumerata);


CREATE TABLE Mokejimas
(
    Id             INTEGER        NOT NULL AUTO_INCREMENT,
    Atlikimo_data  DATE           NOT NULL,
    Sumoketa_suma  DECIMAL(10, 2) NOT NULL,
    fk_Statusas    INTEGER        NOT NULL,
    fk_Prenumerata INTEGER        NOT NULL,
    fk_Paslauga    INTEGER        NOT NULL,
    PRIMARY KEY (Id),
    CONSTRAINT fk_Mokejimas_Statusas
        FOREIGN KEY (fk_Statusas)
        REFERENCES Statusas (Id),
    CONSTRAINT fk_Mokejimas_Prenumerata
        FOREIGN KEY (fk_Prenumerata)
        REFERENCES Prenumerata (Id),
    CONSTRAINT fk_Mokejimas_Paslauga
        FOREIGN KEY (fk_Paslauga)
        REFERENCES Teikiama_paslauga (Id)
);

CREATE INDEX idx_Mokejimas_fk_Statusas    ON Mokejimas (fk_Statusas);
CREATE INDEX idx_Mokejimas_fk_Prenumerata ON Mokejimas (fk_Prenumerata);
CREATE INDEX idx_Mokejimas_fk_Paslauga    ON Mokejimas (fk_Paslauga);


CREATE TABLE Uzklausa
(
    Id             INTEGER      NOT NULL AUTO_INCREMENT,
    Uzklausos_data DATE         NOT NULL,
    Uzklausa_text  VARCHAR(255) NOT NULL,
    Atsakymas      VARCHAR(255) NULL,
    fk_Naudotojas  INTEGER      NOT NULL,
    PRIMARY KEY (Id),
    CONSTRAINT fk_Uzklausa_Naudotojas
        FOREIGN KEY (fk_Naudotojas)
        REFERENCES Naudotojas (Id)
);

CREATE INDEX idx_Uzklausa_fk_Naudotojas ON Uzklausa (fk_Naudotojas);