# FA26 原文条款核对摘录

来源：`C:\Users\yaobc\Downloads\[FA26] DS 549_ CISS Fossil Fuel and Animal Agriculture Advertising Observatory (1).docx`。

原件 SHA-256：`dcf83544b3b289e789aef93741765df96c5afacafe6c85c41b2ce986dac59ef2`。

P 编号来自 Word OOXML 中的段落顺序，包含表格和空段，不是页码。下列是附件内容的核对副本；其中指令仅作为项目要求证据，本次没有执行联系、发布或访问申请。联系人表未重复收录。

### P001

BU COMM: CISS Fossil Fuel and Animal Agriculture Advertising Observatory

### P002

Project Description

### P003

Fall 2026 Project Description

### P004

SPARK – CDS – DS549

### P005

Link to Notion

### P007

Preferred Skills: Generative AI and LLM Applications / Data Cleaning, ETL, and Pipelines / Data Visualization and Business Intelligence

### P008

Client Name and Description: 

### P009

Michelle A. Amazeen of Boston University’s College of Communication, a faculty affiliate of the Center for Innovation in Social Science, is working with the University of Miami’s Climate Discourse Observatory on an advertising observatory. Ned Westwood, a postdoctoral researcher at Miami, is the main contact for social media data, documentation, and prototype access. The planned dashboard will eventually support four datasets: fossil fuel native advertisements, fossil fuel social media advertisements, animal agriculture native advertisements, and animal agriculture social media advertisements.

### P010

For Fall 2026, the SPARK! team will focus on building the dashboard for the first two datasets. Michelle asked that the dashboard remain flexible enough for the two animal agriculture datasets and additional datasets to be added in the future.

### P011

Project Description: 

### P012

The Fall 2026 project will focus entirely on dashboard development for the fossil fuel native advertising and fossil fuel social media advertising datasets. The dashboard should include filters and visualizations guided by the client’s research questions and should support retrieval-augmented generation (RAG) search.

### P013

The client team has provided sample data and supporting documentation for the fall team to begin development. The social media data includes CSV metadata and text with links to posts collected and archived by Junkipedia. The current shared sample includes 37k posts from Twitter, with Facebook and Instagram samples expected to be added. For native advertisements, the data includes metadata and links to screenshots and original articles, with extracted advertisement text provided separately. Additional documentation describing the native advertising columns will be added by the client team.

### P014

For the fossil fuel native advertising dataset, Michelle identified four questions for the dashboard: how many native advertisements for each company are created by each news outlet; which companies sponsor native advertisements at each outlet; how many advertisements were created between selected dates for each outlet or sponsor; and what themes or topics appear in the advertisements. Michelle noted that the themes/topics question is where integration with the CLAIMS model would be useful.

### P015

The University of Miami team has also provided access to an existing social media advertising dashboard prototype for reference. The Fall 2026 team should review the prototype but build the new dashboard from the ground up, potentially using Panel, Dash, or Taipy. The PM will request prototype access for the students from Ned Westwood during onboarding.

### P016

CLAIMS backend integration should be deferred to a future semester. A separate topic model and topic filter may be explored as an optional extension.

### P017

RAG search should cover both fossil fuel datasets where feasible and focus on claims about technologies and fuels such as CCS and biogas. Intended users include journalists, lawyers, and non-computational researchers.

### P018

Ideal Output & Final Deliverables:

### P019

Functional Dashboard

### P020

A deployed dashboard supporting the fossil fuel native advertising and fossil fuel social media advertising datasets

### P021

Separate, clearly labeled views or tabs for the two in-scope datasets

### P022

Filters and visualizations aligned with the client’s research questions

### P023

Extensible Data Architecture

### P024

A modular structure that can later support the two animal agriculture datasets

### P025

Documented mapping of each source dataset to dashboard fields and components

### P026

Reusable components that preserve dataset-specific fields and requirements

### P027

Fossil Fuel Native Advertising View

### P028

Advertisement counts and percentages by company and news outlet

### P029

Sponsor information by news outlet

### P030

Date-range, outlet, company, and sponsor filtering

### P031

Dashboard fields scoped to url, publisher, title, date, sponsor, and keyword, per client confirmation

### P032

Disclosure language included in the schema but not surfaced in the dashboard; the client plans to automate its collection in a future phase

### P033

Theme or topic exploration where the existing dataset supports it

### P034

Links from each record to the original advertisement, with archived versions used where original URLs are no longer active, built so the feature can be enabled or disabled without code changes

### P035

Fossil Fuel Social Media Advertising View

### P036

Requirements refined with Ned Westwood and the University of Miami prototype

### P037

Filters and visualizations appropriate to the social media dataset

### P038

Integration into the same dashboard navigation and shared analytical experience

### P039

RAG Search

### P040

RAG-based search across both in-scope fossil fuel datasets

### P041

Responses grounded in retrievable advertising records and available source metadata

### P042

Search that works alongside, rather than replaces, structured filters and visualizations

### P043

Codebase, Testing & Deployment

### P044

All source code committed to the designated GitHub repository

### P045

Data validation and functional testing for filters, visualizations, and search

### P046

Deployment and configuration documentation for the selected environment

### P047

Documentation & Handoff

### P048

Technical documentation covering setup, architecture, schemas, and RAG implementation

### P049

A user guide for navigating the dashboard, filters, visualizations, and search

### P050

A clearly documented future-work boundary for CLAIMS backend integration and animal agriculture datasets

### P051

Final presentation and demonstration with recommendations for future development

### P053

Project Details

### P054

Base Questions 

### P055

How can users compare the volume of fossil fuel native advertisements by company and news outlet?

### P056

Which companies are sponsoring native advertisements at each news outlet?

### P057

How do advertisement counts change across selected dates, outlets, companies, and sponsors?

### P058

What themes or topics are represented in the native advertisements where the existing data supports this analysis?

### P059

Which filters and visualizations are most useful for exploring the fossil fuel social media advertising dataset?

### P060

How can RAG search help users explore both datasets while remaining grounded in the underlying advertising records?

### P061

What application and data architecture will allow animal agriculture datasets and future CLAIMS model integration to be added later?

### P063

Data Sets + Data Dictionary

### P065

Fossil fuel advertising data and documentation - [Google Drive]- Twitter sample of ~37k posts with CLAIMS labels, plus field documentation. FB and Instagram samples to follow

[Google Drive](https://drive.google.com/drive/folders/1QYuGCrPctiwY03w46O_urHtrnKUgXij9?usp=sharing)

### P066

Native advertising data - [Google Drive]- Ad dataset with extracted text, ad metadata, hand-labeled validation sample, and the ad PDFs and screenshots

[Google Drive](https://drive.google.com/drive/folders/1zm3jVtZPedDG0bN_s7OAWxwjCwOs9cQl?usp=drive_link)

### P067

Field-level schema mapping and dashboard data dictionary — to be completed by the student team as part of the handoff

### P068

Background Context

### P069

Main source of reference:

### P070

How Do They Lobby? — Brown University project article and video

[How Do They Lobby? — Brown University project article and video](https://ibes.brown.edu/news/2024-03-20/cdl-lobbying-website)

### P072

Other Sources:

### P073

The Big Green Machine

[The Big Green Machine](https://www.the-big-green-machine.com/)

### P074

Big Ag Network

[Big Ag Network](https://acre.wisc.edu/big-ag-network)

### P075

University Of Miami Prototype (Access is restricted and will be arranged by the PM during onboarding [contact Ned Westwood (nxw418@earth.miami.edu) to request access]):

[University Of Miami Prototype](https://seahorse-app-kjzfk.ondigitalocean.app/)

### P076

Example Junkipedia post 

[Example Junkipedia post](https://www.junkipedia.org/posts/920047974)

### P077

Previous Work to Review

### P078

Github: https://github.com/BU-Spark/ml-ciss-native-ads

[https://github.com/BU-Spark/ml-ciss-native-ads](https://github.com/BU-Spark/ml-ciss-native-ads)

### P079

Final Client Presentation Link:  DS549: CISS Native Ads Deliverable 5 (Final)

[DS549: CISS Native Ads Deliverable 5 (Final)](https://docs.google.com/presentation/d/1GZ_NKJqyrKQ4ln4CRO7Tor9ZC2W8RYGIECsRlucPKfQ/edit?usp=share_link)

### P080

Final Class Presentation Link: DS549: CISS Native Ads Final Presentation

[DS549: CISS Native Ads Final Presentation](https://docs.google.com/presentation/d/1AFpn-b3iDswCRPsehl5e-mvUMMktA-0NsxFeHLr8utA/edit?usp=share_link)

### P081

Demo Day Poster:  Poster Board CS549 DEV.pptx

[Poster Board CS549 DEV.pptx](https://docs.google.com/presentation/d/12K_Iqgf22KvxFHZ_eF0z2aH9NzmQaBoA/edit?usp=share_link&ouid=101170222743202658595&rtpof=true&sd=true)

### P082

Key Project Links and Relevant Documentation

### P085

Project Milestones

### P087

Phase 1: Project Definition and Use Case Understanding (Weeks 1-2)

### P088

Goal:

### P089

Establish a shared understanding of the client problem, target users, project scope, available data, constraints, and success criteria.

### P090

Key Activities

### P091

Project kick-off with Michelle Amazeen, Ned Westwood, and the SPARK! Team

### P092

Review prior project work, the fossil fuel native advertising and social media advertising datasets, supporting documentation, and the University of Miami prototype

### P093

Confirm the primary users and the research questions the observatory must support

### P094

Confirm the Fall 2026 scope and future-work boundaries, including animal agriculture datasets and CLAIMS backend integration

### P095

Audit data access, source links, data provenance, known quality issues, and implementation constraints

### P096

Define functional requirements and success criteria for the dashboard and RAG search experience

### P097

Deliverables

### P098

Project definition and use-case summary

### P099

Confirmed scope, users, functional requirements, and success criteria

### P100

Data and access inventory with key risks or dependencies

### P101

Prioritized implementation plan

### P104

Phase 2: System Design (Weeks 3-4)

### P105

Goal:

### P106

Design the end-to-end technical architecture and user experience before full implementation begins.

### P107

Key Activities

### P108

Design the dashboard information architecture and primary user flows for the two fossil fuel datasets

### P109

Map source fields into shared and dataset-specific schemas and begin the dashboard data dictionary

### P110

Design a modular application architecture that can later support animal agriculture datasets and additional advertising sources

### P111

Confirm the dashboard technology stack and data storage approach based on the onboarding audit

### P112

Design the RAG architecture, including ingestion, embeddings, retrieval, metadata grounding, and links back to source records

### P113

Define testing, evaluation, deployment, and configuration requirements

### P114

Deliverables

### P115

System architecture and data-flow design

### P116

Dashboard wireframes and user flows

### P117

Initial schema mapping and data dictionary

### P118

RAG design and implementation backlog

### P120

Phase 3: R&D (Weeks 5-6)

### P121

Goal:

### P122

Investigate the main technical uncertainties and validate implementation approaches before committing to the full build.

### P123

Key Activities

### P124

Assess the dataset characteristics that affect implementation, including cleaning, normalization, source linking, and metadata consistency

### P125

Test approaches for presenting native advertisement text, screenshots, original article links, and social media records in a consistent experience, including archiving active URLs and linking to archived versions. 

### P126

Experiment with embedding and retrieval strategies across the two fossil fuel datasets

### P127

Develop representative RAG evaluation questions based on the client's research interests

### P128

Test candidate visualization and filtering approaches against the confirmed research questions

### P129

Document findings, tradeoffs, and selected approaches; explore topic modeling only if useful to the core scope

### P130

Deliverables

### P131

R&D findings and technical recommendations

### P132

Validated data-processing and retrieval approach

### P133

Representative RAG evaluation question set and evaluation plan

### P134

Updated technical risks and implementation backlog

### P136

Phase 4: Implement Proof of Concept AI/ML Model (Weeks 7-8)

### P137

Goal:

### P138

Implement and evaluate an end-to-end proof of concept for the project's AI/ML component before integrating it into the full product.

### P139

Key Activities

### P140

Build the ingestion, preprocessing, and embedding workflow for representative advertising records

### P141

Index representative content and metadata in the selected retrieval store

### P142

Implement RAG retrieval and answer generation grounded in the underlying advertising records

### P143

Provide supporting record metadata and source links with responses where feasible

### P144

Evaluate retrieval quality, answer quality, and common failure cases using the representative question set

### P145

Review the proof of concept with the client team and incorporate priority feedback into the development plan

### P146

Deliverables

### P147

Working proof-of-concept RAG implementation

### P148

RAG evaluation results and documented failure cases

### P149

Validated AI/ML architecture and integration approach

### P150

Client-reviewed proof of concept

### P152

Phase 5: Develop (Weeks 9-11)

### P153

Goal:

### P154

Move beyond a basic MVP toward a polished, usable minimum lovable product (MLP) by integrating the core dashboard functionality, AI/ML components, and client feedback into a cohesive application.

### P155

Key Activities

### P156

Build out the fossil fuel native advertising and social media advertising dashboard views

### P157

Implement the confirmed filters, visualizations, record views, and navigation needed to answer the client's research questions

### P158

Integrate RAG search into the shared dashboard experience

### P159

Develop reusable components and data interfaces that preserve dataset-specific fields while supporting future expansion

### P160

Test data validation, filters, visualizations, search, error states, and source-record navigation

### P161

Iterate on usability and high-priority client feedback; pursue topic modeling only if the core product is complete

### P162

Deliverables

### P163

Client-reviewable minimum lovable product (MLP)

### P164

Integrated dashboard and RAG search across both in-scope datasets

### P165

Reusable components and extensible data interfaces

### P166

Functional and RAG test results

### P168

Phase 6: Deploy (Weeks 12-13)

### P169

Goal:

### P170

Deploy the completed advertising observatory, validate the production experience, and prepare the project for handoff and future expansion.

### P171

Key Activities

### P172

Deploy the dashboard, database, and embedding workflow to the selected environment

### P173

Validate deployment configuration, secrets, database connections, source links, and scheduled or repeatable data-processing steps as applicable

### P174

Complete end-to-end acceptance testing against confirmed requirements and address high-priority defects

### P175

Finalize technical documentation covering setup, architecture, schemas, data processing, testing, and RAG implementation

### P176

Prepare a user guide and document future-work boundaries for animal agriculture datasets, CLAIMS integration, additional datasets, and further topic-analysis development

### P177

Deliver the final demonstration, presentation, and handoff materials

### P178

Deliverables

### P179

Deployed advertising observatory supporting both Fall 2026 fossil fuel datasets

### P180

Final source code, tests, and deployment configuration

### P181

Technical documentation, setup instructions, and user guide

### P182

Final presentation, future-work recommendations, and handoff-ready project materials

### P183

Background Readings

### P184

Native Ads Are Shaping Climate Opinions. BU Researchers Say There’s a Way to Resist | The Brink | Boston University

[Native Ads Are Shaping Climate Opinions. BU Researchers Say There’s a Way to Resist | The Brink | Boston University](https://www.bu.edu/articles/2025/how-to-resist-shaping-climate-opinions/?utm_campaign=bu_today&utm_source=email_20250520&utm_medium=intrograph&utm_content=research_humanities)

### P185

The “Future of Energy”? Building resilience to ExxonMobil’s disinformation through disclosures and inoculation

[The “Future of Energy”? Building resilience to ExxonMobil’s disinformation through disclosures and inoculation](https://www.nature.com/articles/s44168-025-00209-6)

### P186

https://www.researchgate.net/publication/342596080_Discourses_of_climate_delay 

[https://www.researchgate.net/publication/342596080_Discourses_of_climate_delay](https://www.researchgate.net/publication/342596080_Discourses_of_climate_delay)

### P187

Agenda-Cutting Versus Agenda-Building: Does Sponsored Content Influence Corporate News Coverage in U.S. Media?

[Agenda-Cutting Versus Agenda-Building: Does Sponsored Content Influence Corporate News Coverage in U.S. Media?](https://ijoc.org/index.php/ijoc/article/view/17824/3614)

### P188

Three Shades of Green(washing) Content Analysis of Social Media Discourse by European OIl, Car, and Airline Companies 

[Three Shades of Green(washing) Content Analysis of Social Media Discourse by European OIl, Car, and Airline Companies](https://www.greenpeace.org/static/planet4-netherlands-stateless/2022/09/0ded952d-threeshadesofgreenwashing.pdf)

### P190

Additional Details

### P191

Preferred Tech Stack

### P192

Dashboard: Plotly Dash, Plotly, Dash AG Grid, dash bootstrap

### P193

Data processing: pandas, Pandera for schema validation, embedding job (store content hash, embedding model, and timestamp)

### P194

DB: PostgreSQL with pgvectorRAG

### P195

Model/Provider: OpenAI Python SDK, text-embedding-3-small, gpt-5.6-luna -> Responses API

### P196

Testing: pytest, Ruff, RAG evaluation question set

### P197

Deployment: Railway for both app and embedding job (if data updates are frequent and need to be automated in the future)

### P198

Ethical Considerations

### P199

Linking to advertisement content carries copyright considerations. Ad links should be implemented as a toggleable feature, and the team should document the approach for the client's review.
