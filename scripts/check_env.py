import pandas, numpy, faker, sqlalchemy, duckdb

print("pandas", pandas.__version__)
print("numpy", numpy.__version__)
print("sqlalchemy", sqlalchemy.__version__)
print("duckdb", duckdb.__version__)

print(faker.Faker("en_IN").name())            # a random Indian name
print(duckdb.sql("SELECT 42 AS answer").fetchall())   # a real SQL query
