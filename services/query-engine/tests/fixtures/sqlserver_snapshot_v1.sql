use master;
go

if db_id('AtlanteBiSnapshotTest') is not null
begin
  alter database AtlanteBiSnapshotTest set single_user with rollback immediate;
  drop database AtlanteBiSnapshotTest;
end;
go

if exists (select 1 from sys.server_principals where name = 'atlante_snapshot_ro')
  drop login atlante_snapshot_ro;
go

create database AtlanteBiSnapshotTest;
go

create login atlante_snapshot_ro
with password = 'Fixture-Only-Password-42!', check_policy = off;
go

use AtlanteBiSnapshotTest;
go

set ansi_nulls on;
set quoted_identifier on;
set ansi_padding on;
set ansi_warnings on;
set arithabort on;
set concat_null_yields_null on;
set numeric_roundabort off;
go

create schema fixture;
go

create table fixture.ParentEntity (
  TenantCode int not null,
  EntityCode int not null,
  DisplayName nvarchar(120) not null,
  CreatedAt datetime2(3) not null
    constraint DF_ParentEntity_CreatedAt default sysutcdatetime(),
  NormalizedName as lower(DisplayName) persisted,
  constraint PK_ParentEntity primary key (TenantCode, EntityCode),
  constraint UQ_ParentEntity_DisplayName unique (TenantCode, DisplayName),
  constraint CK_ParentEntity_TenantCode check (TenantCode > 0)
);
go

create table fixture.ChildEntity (
  ChildId int identity(100, 5) not null
    constraint PK_ChildEntity primary key,
  TenantCode int not null,
  EntityCode int not null,
  ExternalCode varchar(40) not null,
  IsActive bit not null
    constraint DF_ChildEntity_IsActive default 1,
  constraint FK_ChildEntity_ParentEntity
    foreign key (TenantCode, EntityCode)
    references fixture.ParentEntity(TenantCode, EntityCode)
    on update cascade
    on delete cascade
);
go

create unique nonclustered index UX_ChildEntity_ExternalCode
on fixture.ChildEntity(TenantCode, ExternalCode desc)
include (EntityCode)
where IsActive = 1;
go

create view fixture.vActiveChild
as
select
  child.ChildId,
  child.TenantCode,
  child.EntityCode,
  parent.DisplayName
from fixture.ChildEntity as child
inner join fixture.ParentEntity as parent
  on parent.TenantCode = child.TenantCode
 and parent.EntityCode = child.EntityCode
where child.IsActive = 1;
go

create view fixture.vIndexedChild
with schemabinding
as
select
  ChildId,
  TenantCode,
  EntityCode,
  ExternalCode,
  IsActive
from fixture.ChildEntity;
go

create unique clustered index CUX_vIndexedChild_ChildId
on fixture.vIndexedChild(ChildId);
go

execute sys.sp_addextendedproperty
  @name = N'MS_Description',
  @value = N'Synthetic deterministic metadata fixture',
  @level0type = N'SCHEMA',
  @level0name = N'fixture',
  @level1type = N'TABLE',
  @level1name = N'ParentEntity';
go

create user atlante_snapshot_ro for login atlante_snapshot_ro;
grant select on schema::fixture to atlante_snapshot_ro;
grant view definition on schema::fixture to atlante_snapshot_ro;
go
