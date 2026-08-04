# PII Detection Testing Architecture

## Overview

The PII detection functionality has been refactored to separate concerns:

1. **`pii_detection_logic.py`** - Core PII detection logic (Splunk-independent)
2. **`pii_detection.py`** - Splunk handler that uses the abstracted logic
3. **`test_pii_logic.py`** - Standalone test script for the logic

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PII Detection System                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │   Splunk Handler    │    │     Standalone Testing     │ │
│  │  pii_detection.py   │    │    test_pii_logic.py       │ │
│  │                     │    │                             │ │
│  │ • Splunk-specific   │    │ • Test logic independently │ │
│  │ • REST API handler  │    │ • No Splunk dependencies  │ │
│  │ • Configuration mgmt│    │ • Quick validation         │ │
│  └─────────────────────┘    └─────────────────────────────┘ │
│           │                           │                     │
│           └───────────┬───────────────┘                     │
│                       │                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Core Logic Layer                          │ │
│  │           pii_detection_logic.py                      │ │
│  │                                                       │ │
│  │ • PiiDetectionLogic class                            │ │
│  │ • Detector loading and management                    │ │
│  │ • PII detection algorithms                          │ │
│  │ • Field inference logic                             │ │
│  │ • SEDCMD regex generation                           │ │
│  └─────────────────────────────────────────────────────────┘ │
│                       │                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Custom Detectors                          │ │
│  │           ip_address_detector.py                      │ │
│  │                                                       │ │
│  │ • Custom IP address detector                         │ │
│  │ • Compatible with scrubadub framework                │ │
│  │ • Extensible for additional detectors                │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Files

### Core Logic (`lib/pii_detection_logic.py`)
- **Purpose**: Contains all PII detection logic independent of Splunk
- **Key Class**: `PiiDetectionLogic`
- **Features**:
  - Detector loading and management
  - PII detection using scrubadub
  - Field name inference
  - SEDCMD regex generation
  - Error handling

### Splunk Handler (`bin/pii_detection.py`)
- **Purpose**: Splunk REST API handler
- **Key Class**: `PiiDetection`
- **Features**:
  - Splunk-specific configuration management
  - REST API request/response handling
  - Uses `PiiDetectionLogic` for core functionality
  - Logging and error handling

### Custom Detector (`lib/ip_address_detector.py`)
- **Purpose**: Custom IP address detector for scrubadub
- **Key Classes**: `IpAddressDetector`, `IpAddressFilth`
- **Features**:
  - IPv4 address detection
  - Compatible with scrubadub framework
  - Configurable via UI

### Test Script (`bin/test_pii_logic.py`)
- **Purpose**: Standalone testing of PII detection logic
- **Features**:
  - Tests core logic without Splunk dependencies
  - Demonstrates different detector configurations
  - Handles missing dependencies gracefully

## Testing

### Standalone Testing
```bash
cd splunk-app/ucc-app/bin
python test_pii_logic.py
```

**Expected Output** (when dependencies available):
```
🔍 Testing Abstracted PII Detection Logic
==================================================

1. Testing with default detectors...
Input: User john.doe@example.com logged in from 192.168.1.100
✅ Detected 2 PII items:
   - EmailDetector: 'john.doe@example.com' (position 5-25)
   - IpAddressDetector: '192.168.1.100' (position 35-47)
💡 Suggestion: Detected PII types: EmailDetector, IpAddressDetector...

2. Testing with custom IP detector only...
Input: Multiple IPs: 10.0.0.1, 172.16.0.1, and 8.8.8.8
✅ Detected 3 IP addresses:
   - 10.0.0.1 (position 15-22)
   - 172.16.0.1 (position 24-32)
   - 8.8.8.8 (position 38-45)

🎉 Logic testing completed successfully!
```

### Splunk Integration Testing
The logic is automatically tested when the Splunk app processes PII detection requests through the REST API.

## Benefits

1. **Separation of Concerns**: Core logic is independent of Splunk
2. **Testability**: Can test PII detection without Splunk environment
3. **Maintainability**: Logic is centralized and reusable
4. **Extensibility**: Easy to add new detectors or modify logic
5. **Debugging**: Can isolate issues between logic and Splunk integration

## Adding New Detectors

1. Create detector in `lib/` (see `ip_address_detector.py` for example)
2. Add detector name to default list in `PiiDetectionLogic.__init__()`
3. Add detector option to `globalConfig.json` UI configuration
4. Test using `test_pii_logic.py`

## Configuration

Detectors can be configured via:
- **Splunk UI**: Multi-select dropdown in app configuration
- **Code**: Pass detector list to `PiiDetectionLogic()`
- **Default**: Uses comprehensive list of available detectors 