\# GestUnifServ



\*\*Unified Service Manager\*\* for administrative services of Grupo Energía Bogotá and its subsidiaries.



GestUnifServ will consist of several modules. The first module focuses on:



\*\*Evaluation of terrestrial routes in Colombia.\*\*



This system allows employees to register travel routes, calculate the associated risk, consult relevant news, and generate automated PDF reports.



\## Features



\- Route registration via bot in MS Teams  

\- Automatic risk evaluation by city  

\- Manual review by analyst  

\- Web-based news retrieval  

\- PDF generation and email delivery  



\## Technologies



\- Python, FastAPI, PostgreSQL  

\- Azure Bot Framework (MS Teams)  

\- Scrapy, spaCy, ReportLab  



\## Database Integration



The system uses PostgreSQL to store and manage service data. Initial schema includes:



\- `routes`: Employee travel routes and metadata  

\- `cities`: Risk scores and contextual information  

\- `evaluations`: Analyst reviews and automated assessments  

\- `news`: Relevant articles linked to route context  



\### Database Setup (Development)



```bash

\# Create database and apply schema

psql -U your\_user -d gestunifserv\_db -f db/schema.sql

