# Quick Start Guide

## TL;DR - Get Building Fast

```bash
# Prerequisites: Node.js 18+, Yarn, Python 3.9+
git clone <repository-url>
cd cimplicity-ai-app
pip install splunk-add-on-ucc-framework
yarn run setup
ucc-gen build --source ucc-app -o build/
cp -R build/cim-plicity/* packages/cim-plicity/src/main/resources/splunk/
yarn run build
```

Your Splunk app will be ready in: `packages/cim-plicity/stage/`

## Development Commands

| Command | What it does |
|---------|-------------|
| `pip install splunk-add-on-ucc-framework` | 🔧 Install UCC framework |
| `yarn run setup` | 🚀 First time setup |
| `ucc-gen build --source ucc-app -o build/` | ⚙️ Generate UCC components |
| `cp -R build/cim-plicity/* packages/...` | 📋 Copy UCC files |
| `yarn run build` | 📦 Build production app |
| `yarn run start` | 💻 Start dev servers |
| `yarn run test` | 🧪 Run all tests |
| `yarn run lint` | 🔍 Check code quality |

## Project Layout

```
cimplicity-ai-app/
├── packages/
│   ├── ci-mplicity-home/   # React UI components
│   └── cim-plicity/        # Splunk app (builds to stage/)
├── ucc-app/                # UCC (Universal Configuration Console) source
└── .github/workflows/      # CI/CD automation
```

## Build Outputs

- **Development**: `packages/ci-mplicity-home/demo/`
- **Production**: `packages/cim-plicity/stage/` ← Install this in Splunk
- **Packages**: `dist/*.tar.gz` (from CI/CD)

## Common Issues

### Build Fails?
```bash
yarn cache clean
rm -rf node_modules
yarn install
yarn run build
```

### Need to test just one component?
```bash
cd packages/ci-mplicity-home
yarn test -- ComponentName
```

### Want to see changes live?
```bash
yarn run start  # Auto-reloads on file changes
```

## CI/CD Pipeline

Every push triggers:
1. **Python tests** → Runs `pytest tests/`
2. **UCC Generation** → Creates credential management components
3. **Build** → Creates Splunk app package
4. **AppInspect** → Splunk validation (CLI + API)
5. **Release** → Publishes to GitHub (on version tags)

Jest unit tests and ESLint are local-only today (`yarn run test`, `yarn run lint`); run them before pushing.

## Version Tags

```bash
git tag v1.2.3
git push origin v1.2.3  # Triggers release build
```

## Need Help?

- 📖 Full docs: [`BUILD_GUIDE.md`](BUILD_GUIDE.md)
- 🐛 Issues: Check GitHub Actions logs
- 💬 Questions: Contact me at splunk@livehybrid.com

---

**Ready to develop?** Run `yarn run start` and open your browser! 