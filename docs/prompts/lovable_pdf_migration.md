# Migration: Switch from Supabase PDF Storage to API

## Background

Currently, the frontend uploads PDFs to Supabase storage and passes the Supabase URL to the API. This creates a problem: contracts uploaded directly via the API (without the frontend) don't have PDFs in Supabase.

We've updated the ComplyFlow API to handle PDF storage directly. The API now:
1. Stores uploaded PDFs in its own object storage (Railway bucket)
2. Provides a `GET /contracts/{id}/pdf` endpoint to download PDFs

## What Needs to Change

### 1. Remove Supabase PDF Upload from Contract Upload Flow

**Current flow (REMOVE):**
```
User selects PDF → Upload to Supabase → Get Supabase URL → Send to API with pdf_url
```

**New flow:**
```
User selects PDF → Send directly to API (no Supabase)
```

**Changes needed:**
- Remove the Supabase storage upload code from the contract upload flow
- The API upload endpoint `POST /contracts/upload` only needs the file (no `pdf_url` parameter)
- The API will store the PDF and return `pdf_url` in the response (this is now the internal storage path, not a URL)

### 2. Update PDF Display to Use API Endpoint

**Current flow (REMOVE):**
```
Get contract → Read pdf_url field → Fetch from Supabase URL
```

**New flow:**
```
Get contract → Call GET /contracts/{id}/pdf → Display PDF
```

**New API Endpoint:**
```
GET /contracts/{contract_id}/pdf
Headers: X-API-Key: <api_key>
Response: PDF file (application/pdf)
```

**Changes needed:**
- Replace any direct Supabase URL usage with a call to `/contracts/{id}/pdf`
- The PDF viewer should use the API endpoint URL
- The endpoint returns the PDF with `Content-Disposition: inline; filename="original_name.pdf"` so it can be displayed inline or downloaded

### 3. Update the `getPdfUrl` Function

In `src/lib/api.ts`, there's likely a function that gets the PDF URL. Update it to:

```typescript
export const getPdfUrl = (contractId: string): string => {
  // Return the API endpoint URL for PDF download
  return `${API_BASE_URL}/contracts/${contractId}/pdf`;
};
```

Or if you need to fetch with auth headers:

```typescript
export const fetchContractPdf = async (contractId: string): Promise<Blob> => {
  const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/pdf`, {
    headers: {
      'X-API-Key': API_KEY,
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('PDF not found for this contract');
    }
    throw new Error('Failed to fetch PDF');
  }

  return response.blob();
};
```

### 4. Handle Missing PDFs Gracefully

Some existing contracts may not have PDFs (uploaded before this feature). The API returns:

```json
{
  "detail": "PDF not found. This contract may have been uploaded before PDF storage was enabled."
}
```

Status code: 404

**UI should:**
- Show a helpful message like "No PDF available for this contract"
- Hide the "View PDF" button for contracts without PDFs
- You can check if a PDF exists by looking at the `pdf_url` field in the contract record (null means no PDF)

### 5. Remove Supabase Storage Dependencies (Optional)

If Supabase storage is no longer needed for anything else:
- Remove the Supabase storage client/config
- Remove the `contracts` bucket reference
- Clean up any Supabase-related environment variables

## Summary of API Changes

| Old | New |
|-----|-----|
| Upload PDF to Supabase first | Just send PDF to API |
| Pass `pdf_url` to upload endpoint | Don't pass `pdf_url` (API generates it) |
| Fetch PDF from Supabase URL | Fetch from `GET /contracts/{id}/pdf` |
| `pdf_url` is a Supabase URL | `pdf_url` is internal storage path (don't use directly) |

## Testing Checklist

- [ ] Upload a new contract and verify PDF is stored
- [ ] View the PDF in the contract editor
- [ ] Verify old contracts without PDFs show appropriate message
- [ ] Remove Supabase storage code
- [ ] Verify no Supabase errors in console
