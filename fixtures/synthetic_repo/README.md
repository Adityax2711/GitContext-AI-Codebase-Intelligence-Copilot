# SynthStore API & Engine

SynthStore is a sample microservice demonstrating e-commerce authentication and payment pipelines.

## Architecture

The system consists of three core components:
1. **Authentication Service**: Token-based session management and cryptographic password verification.
2. **Payment Gateway**: Stripe-integrated billing and recurring subscription processor.
3. **Storage Engine**: Transactional SQLite/Postgres persistence layer with connection pooling.

## Installation and Setup

To install SynthStore dependencies, run:
```bash
pip install -r requirements.txt
```

## Security and Secrets
All API tokens must be passed via environment variables. Do not commit `.env` files.
