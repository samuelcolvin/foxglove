create table if not exists organisations (
  id serial primary key,
  name varchar(255) not null
);

create table if not exists users (
  id serial primary key,
  org int not null references organisations on delete cascade,
  first_name varchar(255),
  last_name varchar(255),
  email varchar(255)
);
create unique index if not exists user_email on users using btree (org, email);
