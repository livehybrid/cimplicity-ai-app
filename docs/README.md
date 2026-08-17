# CiMplicity Splunk App Documentation

Welcome to the CiMplicity Splunk App documentation! This directory contains all the documentation you need to understand, build, and contribute to the project.

## 📚 Documentation Index

### Getting Started
- **[Quick Start Guide](QUICK_START.md)** - Get up and running in minutes
- **[Build Guide](BUILD_GUIDE.md)** - Comprehensive build and development documentation

### Product
- **[Product Brief](PRODUCT_BRIEF.md)** - What the app does and its MVP feature set
- **[Problem Solved](PROBLEM_SOLVED.md)** - The onboarding pain points the app addresses

### API Reference
- **[AI Detection Endpoint](AI_DETECTION_ENDPOINT.md)** - AI-assisted field extraction REST endpoint
- **[PII Detection Endpoint](PII_DETECTION_ENDPOINT.md)** - PII scanning REST endpoint
- **[CIM Mapping Endpoint](CIM_MAPPING_ENDPOINT.md)** - AI-assisted CIM mapping REST endpoint (dynamic CIM model loading)
- **[MCP Tools](MCP_TOOLS.md)** - Splunk MCP Server tool registration and per-tool contracts

### For Developers
- **Quick Start**: For immediate development setup
- **Build Guide**: Deep dive into build processes, CI/CD, and troubleshooting

### For DevOps/CI/CD
- **Build Guide**: Contains detailed CI/CD pipeline documentation
- **GitHub Actions**: Located in `../.github/workflows/splunk-app-ci.yml`

## 🔧 Project Overview

**CiMplicity** is a Splunk app that helps with data onboarding and CIM (Common Information Model) mapping. The project is structured as a monorepo with multiple packages:

### Key Components
- **React UI Components** (`ci-mplicity-home`): Frontend interface built with Splunk React UI
- **Splunk App Core** (`cim-plicity`): Backend Python scripts and Splunk configuration
- **Automated CI/CD**: GitHub Actions for build, test, and deployment

### Technology Stack
- **Frontend**: React, Splunk React UI, Webpack, Babel
- **Backend**: Python, Splunk REST APIs
- **Configuration**: UCC Framework (Universal Configuration Console)
- **Build Tools**: Lerna (monorepo), Yarn, Node.js
- **Quality**: Jest (testing), ESLint (linting), Prettier (formatting)
- **CI/CD**: GitHub Actions, Splunk AppInspect

## 🚀 Quick Commands

```bash
# Install UCC framework
pip install splunk-add-on-ucc-framework

# First time setup
yarn run setup

# Generate UCC components
ucc-gen build --source ucc-app -o build/
cp -R build/cim-plicity/* packages/cim-plicity/src/main/resources/splunk/

# Build for production
yarn run build

# Start development
yarn run start

# Run tests
yarn run test

# Check code quality
yarn run lint
```

## 📦 Build Outputs

After building, you'll find:
- **Production App**: `packages/cim-plicity/stage/` (ready for Splunk installation)
- **Demo/Development**: `packages/ci-mplicity-home/demo/`
- **Distribution Packages**: `dist/*.tar.gz` (from CI/CD)

## 🔄 CI/CD Pipeline

Every code push triggers our automated pipeline:

1. **Python tests** → Runs `pytest tests/`
2. **Build** → Compiles and packages the Splunk app (UCC generation, Webpack, `ucc-gen package`)
3. **AppInspect** → Validates against Splunk standards (CLI + API)
4. **Release** → Publishes releases for version tags

Jest unit tests and ESLint are local-only (`yarn run test`, `yarn run lint`); run them before pushing.

## 🆘 Getting Help

### Common Issues
- **Build fails**: Try clearing cache with `yarn cache clean && rm -rf node_modules && yarn install`
- **Tests fail**: Check individual test output with `yarn test -- --verbose`
- **CI/CD issues**: Review GitHub Actions logs and AppInspect reports

### Resources
- [Splunk React UI Documentation](https://splunkui.splunk.com/)
- [Splunk App Development](https://dev.splunk.com/)
- [Lerna Documentation](https://lerna.js.org/)
- [Yarn Workspaces](https://classic.yarnpkg.com/en/docs/workspaces/)

### Support
- **Issues**: Create GitHub issues for bugs or feature requests
- **Questions**: Reach out to the development team
- **Contributions**: See build guide for development workflow

---

📋 **Start here**: [`QUICK_START.md`](QUICK_START.md) | 📖 **Detailed docs**: [`BUILD_GUIDE.md`](BUILD_GUIDE.md)