# ComplyFlow Frontend Specification

## Overview

Build a simple, elegant contract intake interface for legal teams. Users upload PDFs, review AI-extracted metadata, make corrections, and mark contracts as reviewed. All corrections are tracked for ML training.

**Target Platform:** Lovable AI
**Tech Stack:** React, TypeScript, Tailwind CSS, shadcn/ui

---

## Core User Flow

```
Upload PDF → Processing (30-60s) → View/Edit Extracted Data → Mark Reviewed
```

Only 2 pages:
1. **Upload Page** (`/`) - Drop PDF, see processing state
2. **Contract Editor** (`/contracts/:id`) - Edit fields, mark reviewed

---

## API Integration

### Base URL
```
https://complyflow-production.up.railway.app
```

### Authentication
All API calls require the `X-API-Key` header:
```typescript
const API_KEY = import.meta.env.VITE_API_KEY;

const apiClient = {
  headers: {
    'X-API-Key': API_KEY,
  }
};
```

### Endpoints Used

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/contracts/upload` | Upload PDF, returns extracted data |
| GET | `/contracts/{id}` | Get contract by ID |
| PATCH | `/contracts/{id}/review` | Mark as reviewed |
| PATCH | `/contracts/{id}/fields` | Update individual fields (TO BE ADDED) |

---

## Page 1: Upload (`/`)

Simple upload interface with processing feedback.

### Layout
- Centered card (max-width 600px)
- Logo "ComplyFlow" at top
- Dropzone area
- Processing state below

### Dropzone Component
```
┌─────────────────────────────────────┐
│                                     │
│         📄 Drop PDF here            │
│      or click to browse             │
│                                     │
│      Accepts: .pdf (max 10MB)       │
│                                     │
└─────────────────────────────────────┘
```

- Dashed border, rounded corners
- Hover state: border turns blue
- Drag-over state: background turns light blue
- Accept only `.pdf` files
- Validate file size < 10MB

### After File Selected
```
┌─────────────────────────────────────┐
│  📄 ServiceAgreement.pdf            │
│     2.4 MB                          │
│                                     │
│  [Upload & Extract]                 │
└─────────────────────────────────────┘
```

### Processing State
```
┌─────────────────────────────────────┐
│                                     │
│         ⏳ Processing...            │
│                                     │
│   Extracting contract metadata      │
│   This takes about 30-60 seconds    │
│                                     │
│         [Cancel]                    │
└─────────────────────────────────────┘
```

- Show spinner animation
- Disable page navigation
- On success: redirect to `/contracts/{contract_id}`
- On error: show error message with retry button

### API Call
```typescript
const uploadContract = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/contracts/upload`, {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json(); // ContractUploadResponse
};
```

### Error States
| Status | Message |
|--------|---------|
| 400 | "Invalid file. Please upload a PDF." |
| 401 | "Unauthorized. Check API key." |
| 413 | "File too large. Maximum size is 10MB." |
| 502 | "AI extraction failed. Please try again." |
| 504 | "Request timed out. Please try again." |

---

## Page 2: Contract Editor (`/contracts/:id`)

View and edit extracted metadata. Track all corrections.

### Layout
```
┌─────────────────────────────────────────────────────────┐
│ ← Back                                    [Mark Reviewed]│
├─────────────────────────────────────────────────────────┤
│ ServiceAgreement.pdf                                    │
│ Status: 🟡 Under Review                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ PARTIES                                                 │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ • Acme Corporation                              [×] │ │
│ │ • BigCo Inc                                     [×] │ │
│ │ [+ Add Party]                                       │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ CONTRACT TYPE                                           │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Services Agreement                              ▼   │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌──────────────────────┐  ┌──────────────────────────┐ │
│ │ AGREEMENT DATE       │  │ EFFECTIVE DATE           │ │
│ │ ┌──────────────────┐ │  │ ┌──────────────────────┐ │ │
│ │ │ Jan 15, 2024  📅 │ │  │ │ Feb 1, 2024       📅 │ │ │
│ │ └──────────────────┘ │  │ └──────────────────────┘ │ │
│ └──────────────────────┘  └──────────────────────────┘ │
│                                                         │
│ ┌──────────────────────┐  ┌──────────────────────────┐ │
│ │ EXPIRATION DATE      │  │ NOTICE DEADLINE          │ │
│ │ ┌──────────────────┐ │  │ ┌──────────────────────┐ │ │
│ │ │ Jan 31, 2025  📅 │ │  │ │ Oct 31, 2024      📅 │ │ │
│ │ └──────────────────┘ │  │ └──────────────────────┘ │ │
│ └──────────────────────┘  └──────────────────────────┘ │
│                                                         │
│ GOVERNING LAW                                           │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ State of Delaware                                   │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ NOTICE PERIOD                                           │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 90 days prior written notice                        │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ RENEWAL TERM                                            │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ This Agreement shall automatically renew for        │ │
│ │ successive one (1) year periods unless either       │ │
│ │ party provides written notice...                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Editable Fields

| Field | Input Type | Notes |
|-------|------------|-------|
| `parties` | Tag input | Add/remove party names |
| `contract_type` | Dropdown | 26 predefined types (see below) |
| `agreement_date` | Date picker | Calendar popup |
| `effective_date` | Date picker | Calendar popup |
| `expiration_date` | Date picker | Calendar popup |
| `notice_deadline` | Date picker | Calendar popup (derived, but editable) |
| `first_renewal_date` | Date picker | Calendar popup |
| `governing_law` | Text input | Free text |
| `notice_period` | Text input | Free text |
| `renewal_term` | Textarea | Multi-line, expandable |

### Contract Types (Dropdown Options)
```typescript
const CONTRACT_TYPES = [
  "affiliate-license-licensor",
  "affiliate-license-licensee",
  "co-branding",
  "collaboration",
  "development",
  "distributor",
  "endorsement",
  "franchise",
  "hosting",
  "ip-license-licensor",
  "ip-license-licensee",
  "joint-venture",
  "license",
  "maintenance",
  "manufacturing",
  "marketing",
  "non-compete",
  "outsourcing",
  "promotion",
  "reseller",
  "services",
  "sponsorship",
  "supply",
  "strategic-alliance",
  "transportation",
  "other"
];
```

### Date Picker Behavior
- Click field to open calendar popup
- Display format: "Jan 15, 2024"
- Allow clearing (set to null)
- Show "Not specified" for null dates

### Parties Input (Tag-style)
- Show each party as a removable tag
- "Add Party" button opens text input
- Enter to add, Escape to cancel
- X button to remove

### Auto-save vs Manual Save

**Recommended: Auto-save with debounce**
- Save 1 second after user stops typing
- Show subtle "Saving..." indicator
- Show "Saved" checkmark on success
- No explicit save button needed

### Tracking Corrections

When a field is edited, before saving to Airtable, log the correction:

```typescript
interface Correction {
  contract_id: string;
  field_name: string;
  original_value: string;
  corrected_value: string;
  corrected_at: string; // ISO timestamp
}

const saveFieldWithCorrection = async (
  contractId: string,
  fieldName: string,
  originalValue: any,
  newValue: any
) => {
  // Only log if value actually changed
  if (JSON.stringify(originalValue) === JSON.stringify(newValue)) {
    return;
  }

  await fetch(`${API_URL}/contracts/${contractId}/fields`, {
    method: 'PATCH',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      field_name: fieldName,
      original_value: originalValue,
      new_value: newValue,
    }),
  });
};
```

### Mark as Reviewed

Button in top-right corner:
- Shows "Mark as Reviewed" when status is `under_review`
- On click: confirm dialog "Mark this contract as reviewed?"
- On confirm: PATCH to `/contracts/{id}/review`
- On success: button changes to "✓ Reviewed" (disabled)
- Status badge changes from yellow to green

### Status Badge
```typescript
const StatusBadge = ({ status }: { status: string }) => {
  if (status === 'reviewed') {
    return <Badge className="bg-green-100 text-green-800">Reviewed</Badge>;
  }
  return <Badge className="bg-yellow-100 text-yellow-800">Under Review</Badge>;
};
```

### Back Button
- Returns to upload page (`/`)
- If there are unsaved changes, show confirmation dialog

---

## New API Endpoint Needed

### PATCH `/contracts/{id}/fields`

Update a single field and log the correction.

**Request:**
```json
{
  "field_name": "expiration_date",
  "original_value": "2024-12-01",
  "new_value": "2025-01-15"
}
```

**Response:**
```json
{
  "success": true,
  "field_name": "expiration_date",
  "new_value": "2025-01-15",
  "correction_logged": true
}
```

**Backend behavior:**
1. Update the field in Contracts table
2. Create record in Corrections table:
   - `contract_id`: link to contract
   - `field_name`: "expiration_date"
   - `original_value`: "2024-12-01"
   - `corrected_value`: "2025-01-15"
   - `corrected_at`: now()

---

## Airtable Schema Update

### New Table: Corrections

| Field | Type | Description |
|-------|------|-------------|
| contract | Link to Contracts | Which contract was corrected |
| field_name | Single line text | Field that was changed |
| original_value | Long text | AI-extracted value (JSON string) |
| corrected_value | Long text | Human-corrected value (JSON string) |
| corrected_at | Date with time | When correction was made |

This table builds your ML training dataset over time.

---

## Data Types

### Contract Record (from API)
```typescript
interface ContractRecord {
  id: string;
  fields: {
    filename: string;
    parties: string;              // JSON: '["Party A", "Party B"]'
    contract_type: string;
    agreement_date: string | null;
    effective_date: string | null;
    expiration_date: string | null;
    expiration_type: string;
    notice_deadline: string | null;
    first_renewal_date: string | null;
    governing_law: string | null;
    notice_period: string | null;
    renewal_term: string | null;
    status: 'under_review' | 'reviewed';
    reviewed_at: string | null;
  };
  created_time: string;
}
```

### Parsed Contract (for UI)
```typescript
interface ParsedContract {
  id: string;
  filename: string;
  parties: string[];              // Parsed from JSON
  contractType: string;
  agreementDate: Date | null;
  effectiveDate: Date | null;
  expirationDate: Date | null;
  expirationType: string;
  noticeDeadline: Date | null;
  firstRenewalDate: Date | null;
  governingLaw: string;
  noticePeriod: string;
  renewalTerm: string;
  status: 'under_review' | 'reviewed';
  reviewedAt: Date | null;
  createdAt: Date;
}

// Parse function
const parseContract = (record: ContractRecord): ParsedContract => ({
  id: record.id,
  filename: record.fields.filename,
  parties: JSON.parse(record.fields.parties || '[]'),
  contractType: record.fields.contract_type,
  agreementDate: record.fields.agreement_date ? new Date(record.fields.agreement_date) : null,
  // ... etc
});
```

---

## UI Components Needed

### From shadcn/ui
- `Button` - Primary actions
- `Card` - Container for content
- `Badge` - Status indicators
- `Input` - Text fields
- `Textarea` - Multi-line text
- `Select` - Dropdown for contract type
- `Calendar` + `Popover` - Date picker
- `Dialog` - Confirmation modals
- `Toast` - Success/error notifications
- `Skeleton` - Loading states

### Custom Components
- `FileDropzone` - Drag-and-drop upload
- `PartyInput` - Tag-style party editor
- `DateField` - Date picker with label
- `EditableField` - Wrapper with auto-save
- `ProcessingOverlay` - Full-screen loading state

---

## Design Guidelines

### Colors
- Primary: Blue-600 (`#2563EB`)
- Success: Green-600 (`#16A34A`)
- Warning: Yellow-500 (`#EAB308`)
- Error: Red-600 (`#DC2626`)
- Background: Gray-50 (`#F9FAFB`)
- Card: White
- Text: Gray-900

### Typography
- Font: Inter (or system)
- Headings: Semibold
- Labels: Medium, text-sm, text-gray-600
- Body: Regular, text-gray-900

### Spacing
- Page padding: 24px (p-6)
- Card padding: 24px (p-6)
- Field gap: 16px (gap-4)
- Section gap: 24px (gap-6)

### Responsive
- Mobile: Single column, full width
- Desktop: Two-column grid for date fields
- Max content width: 800px, centered

---

## Environment Variables

```env
VITE_API_URL=https://complyflow-production.up.railway.app
VITE_API_KEY=your-api-key-here
```

---

## Success Criteria

- [ ] Can upload a PDF and see processing state
- [ ] Redirects to editor after successful upload
- [ ] Can view all extracted fields
- [ ] Can edit text fields (governing_law, notice_period, renewal_term)
- [ ] Can edit dates with calendar picker
- [ ] Can add/remove parties
- [ ] Can change contract type from dropdown
- [ ] Edits auto-save with visual feedback
- [ ] Can mark contract as reviewed
- [ ] Clean, professional design
- [ ] Works on mobile

---

## Build Order

1. Set up project with Vite + React + TypeScript + Tailwind + shadcn/ui
2. Create API client with auth headers
3. Build Upload page with dropzone
4. Build Contract Editor page with read-only fields
5. Add editing capability field by field
6. Add auto-save with correction tracking
7. Add Mark as Reviewed functionality
8. Polish: loading states, error handling, responsive design
