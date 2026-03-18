CREATE TABLE [dbo].[content] (
[id] bigint NOT NULL IDENTITY(1,1),
[platform_id] int NOT NULL,
[external_id] nvarchar(150) NOT NULL,
[keyword] nvarchar(255),
[geo] nvarchar(100),
[text_content] nvarchar(max),
[media_type] nvarchar(50),
[url] nvarchar(2000),
[created_at] datetime2(7),
[author_id] bigint,
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[scrape_log] (
[id] int NOT NULL IDENTITY(1,1),
[platform] nvarchar(100),
[identifier] nvarchar(500),
[status] int,
[extracted_at] datetime2(7),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[raw_data_archive] (
[id] int NOT NULL IDENTITY(1,1),
[source_table] nvarchar(100) NOT NULL,
[source_id] bigint NOT NULL,
[raw_data] nvarchar(max),
[created_at] datetime2(7) DEFAULT (sysutcdatetime()),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[authors] (
[id] bigint NOT NULL IDENTITY(1,1),
[platform_id] int NOT NULL,
[external_author_id] nvarchar(150),
[username] nvarchar(200),
[full_name] nvarchar(200),
[follower_count] int,
[is_verified] bit,
[profile_pic_url] nvarchar(2000),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[trends] (
[id] int NOT NULL IDENTITY(1,1),
[platform_id] int,
[topic] nvarchar(500),
[growth] float(53),
[keyword] nvarchar(255),
[geo] nvarchar(100),
[extracted_at] datetime2(7),
[extra_data] nvarchar(max),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[auth_tokens] (
[id] int NOT NULL IDENTITY(1,1),
[token] nvarchar(500) NOT NULL,
[token_hash] AS (CONVERT([varbinary](32),hashbytes('SHA2_256',[token]))) PERSISTED NOT NULL,
[user_id] int NOT NULL,
[created_at] datetime2(7) DEFAULT (sysutcdatetime()),
[expires_at] datetime2(7) NOT NULL,
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[otp_codes] (
[id] int NOT NULL IDENTITY(1,1),
[user_id] int,
[code] nvarchar(20),
[created_at] datetime2(7) DEFAULT (sysutcdatetime()),
[used] bit DEFAULT ((0)),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[platforms] (
[id] int NOT NULL IDENTITY(1,1),
[name] nvarchar(50) NOT NULL,
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[content_hashtags] (
[content_id] bigint NOT NULL,
[hashtag_id] int NOT NULL,
PRIMARY KEY ([content_id], [hashtag_id])
);

CREATE TABLE [dbo].[users] (
[id] int NOT NULL IDENTITY(1,1),
[email] nvarchar(320) NOT NULL,
[role] nvarchar(50) DEFAULT ('trends'),
[created_at] datetime2(7) DEFAULT (sysutcdatetime()),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[scrape_errors] (
[id] int NOT NULL IDENTITY(1,1),
[platform] nvarchar(100),
[keyword] nvarchar(255),
[url] nvarchar(2000),
[status] int,
[reason] nvarchar(max),
[extracted_at] datetime2(7),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[hashtags] (
[id] int NOT NULL IDENTITY(1,1),
[tag] nvarchar(255),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[token_usage] (
[id] int NOT NULL IDENTITY(1,1),
[platform] nvarchar(100) NOT NULL,
[keyword] nvarchar(255),
[units_charged] float(53) DEFAULT ((0)),
[geo] nvarchar(100),
[created_at] datetime2(7) DEFAULT (sysutcdatetime()),
PRIMARY KEY ([id])
);

CREATE TABLE [dbo].[content_metrics] (
[id] bigint NOT NULL IDENTITY(1,1),
[content_id] bigint NOT NULL,
[likes] int DEFAULT ((0)),
[comments] int DEFAULT ((0)),
[shares] int DEFAULT ((0)),
[views] int DEFAULT ((0)),
[saves] int DEFAULT ((0)),
PRIMARY KEY ([id])
);


ALTER TABLE [dbo].[content]
ADD CONSTRAINT []
FOREIGN KEY ([author_id])
REFERENCES [dbo].[authors]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[content]
ADD CONSTRAINT []
FOREIGN KEY ([platform_id])
REFERENCES [dbo].[platforms]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[authors]
ADD CONSTRAINT []
FOREIGN KEY ([platform_id])
REFERENCES [dbo].[platforms]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[trends]
ADD CONSTRAINT []
FOREIGN KEY ([platform_id])
REFERENCES [dbo].[platforms]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[auth_tokens]
ADD CONSTRAINT []
FOREIGN KEY ([user_id])
REFERENCES [dbo].[users]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[otp_codes]
ADD CONSTRAINT []
FOREIGN KEY ([user_id])
REFERENCES [dbo].[users]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[content_hashtags]
ADD CONSTRAINT []
FOREIGN KEY ([content_id])
REFERENCES [dbo].[content]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[content_hashtags]
ADD CONSTRAINT []
FOREIGN KEY ([hashtag_id])
REFERENCES [dbo].[hashtags]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



ALTER TABLE [dbo].[content_metrics]
ADD CONSTRAINT []
FOREIGN KEY ([content_id])
REFERENCES [dbo].[content]([id])
ON DELETE NO ACTION
ON UPDATE NO ACTION;



