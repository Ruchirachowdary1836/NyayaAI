# Hosted corpus and attribution

The Render API image downloads and indexes the AILA 2019 Precedent & Statute Retrieval Task dataset from Zenodo record [10.5281/zenodo.4063986](https://doi.org/10.5281/zenodo.4063986). The record describes 2,914 Supreme Court of India case documents and 197 statute descriptions and marks the dataset **CC BY 4.0**. The build verifies the published archive checksum before processing it.

Attribution: Paheli Bhattacharya, Kripabandhu Ghosh, Saptarshi Ghosh, Arindam Pal, Parth Mehta, Arnab Bhattacharya, and Prasenjit Majumder, *AILA 2019 Precedent & Statute Retrieval Task*, https://doi.org/10.5281/zenodo.4063986, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). NyayaAI normalizes, cleans, and chunks the source documents for retrieval and evaluates the official 50 queries against the provided precedent and statute relevance judgments.

The hosted corpus is a research benchmark snapshot, not a complete or current legal database. It can contain omissions, outdated law, and source-text errors; verify every result against authoritative, current legal sources. Generated responses are assistive only and are not legal advice. The source archive is fetched during Docker image build and is not copied into the Git repository.
