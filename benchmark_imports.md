# Marktstammdatenregister der Bundesnetzagentur




## benchmark


### Import EinheitenWind and EinheitenSolar

System: Ryzen 5 3600 (6 core), Python 3.11, SATA-SSD, postgres 15 docker

`select count(*) from einheitensolar;` : 3.180.113

1. with 1 processes no batch: > 30 Minutes
2. with 8 processes batch-size 10000 :  117 s
3. with 8 processes batch-size 5000 :   112 s
4. with 8 processes batch-size 1000 :   113 s
5. with 4 processes batch-size 1000 :   184 s 
6. with 12 processes batch-size 1000 :  96 s

System: Ryzen 7 4750U (8 core, mobile), Python 3.11, SATA-SSD, postgres 15 docker

1. with 16 processes batch-size 1000 :   125 s
2. with 8 processes batch-size 1000 :   168 s
