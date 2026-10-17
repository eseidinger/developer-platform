SET search_path=ag_catalog,public;
SELECT * FROM cypher('dependencies', $$
  MATCH (a)-[:DEPENDS]->(b)
  RETURN a.name,b.name
$$) AS (component agtype, dependency agtype);
