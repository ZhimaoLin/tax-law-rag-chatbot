import csv
from datetime import datetime
from neo4j import GraphDatabase

from config import Config


kg = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD))
kg.verify_connectivity()


csv_data = []
with open("./data/tax_data.csv", "r") as file:
    csv_reader = csv.DictReader(file)
    for row in csv_reader:
        csv_data.append(row)

node_creation_cypher = """
MERGE (entity:Entity {name: $entity})
MERGE (taxpayer_type:TaxpayerType {name: $taxpayer_type})
MERGE (year:Year {name: $year})
MERGE (date:Date {name: $date})
MERGE (income_source:IncomeSource {name: $income_source})
MERGE (deduction_type:DeductionType {name: $deduction_type})
MERGE (state:State {name: $state})
MERGE (income:Income {amount: $income})
MERGE (deductions:Deductions {amount: $deductions})
MERGE (tax_rate:TaxRate {amount: $tax_rate})
MERGE (tax_owed:TaxOwed {amount: $tax_owed})

CREATE (entity)-[:HAS_TAXPAYER_TYPE]->(taxpayer_type)
CREATE (entity)-[:FILL_TAX_IN]->(year)
CREATE (entity)-[:PAID_TAX_ON]->(date)
CREATE (entity)-[:HAS_INCOME_SOURCE]->(income_source)
CREATE (entity)-[:HAS_DEDUCTION_TYPE]->(deduction_type)
CREATE (entity)-[:IN_STATE]->(state)
CREATE (entity)-[:HAS_INCOME]->(income)
CREATE (entity)-[:HAS_DEDUCTIONS]->(deductions)
CREATE (entity)-[:HAS_TAX_RATE]->(tax_rate)
CREATE (entity)-[:HAS_TAX_OWED]->(tax_owed)
"""


with kg.session(database=Config.NEO4J_DATABASE) as session:
    for i, row in enumerate(csv_data):
        row["Tax Year"] = int(row["Tax Year"])
        row["Transaction Date"] = datetime.strptime(row["Transaction Date"], "%Y-%m-%d").date()
        row["Deductions"] = round(float(row["Deductions"]), 2)
        row["Income"] = round(float(row["Income"]), 2)
        row["Tax Rate"] = round(float(row["Tax Rate"]), 2)
        row["Tax Owed"] = round(float(row["Tax Owed"]), 2)
        print(row)

        session.run(
            node_creation_cypher,
            entity="Entity" + str(i),
            taxpayer_type=row["Taxpayer Type"],
            year=row["Tax Year"],
            date=row["Transaction Date"],
            income_source=row["Income Source"],
            deduction_type=row["Deduction Type"],
            state=row["State"],
            income=row["Income"],
            deductions=row["Deductions"],
            tax_rate=row["Tax Rate"],
            tax_owed=row["Tax Owed"],
        )
