
import React, { useState } from "react";
import { UploadCloud, FileText, LoaderCircle } from "lucide-react";
import "../Pdf_uploader/Pdf_uplaoder.css";
import API from "../../api/axiosInstance";

const Pdf_uploader = ({ onUpload }) => {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0];

    setError("");

    if (!selectedFile) return;

    if (
      selectedFile.type !== "application/pdf" &&
      !selectedFile.name.toLowerCase().endsWith(".pdf")
    ) {
      setError("Please select a PDF file.");
      setFile(null);
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      setError("PDF size must be less than 10 MB.");
      setFile(null);
      return;
    }

    setFile(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a PDF first.");
      return;
    }

    const formData = new FormData();

    formData.append("title", file.name);
    formData.append("pdf_file", file);

    try {
      setLoading(true);
      setError("");

      const response = await API.post("pdfs/", formData);

      console.log("Upload response:", response.data);

      // Extract the document object from API response
      const uploadedDocument = response.data.document;

      if (!uploadedDocument || !uploadedDocument.id) {
        throw new Error("Document ID was not returned by the backend.");
      }

      console.log("Uploaded document:", uploadedDocument);
      console.log("Uploaded document ID:", uploadedDocument.id);

      // Pass only the document object to App.jsx
      if (onUpload) {
        onUpload(uploadedDocument);
      }

      setFile(null);

    } catch (err) {
      const responseData = err.response?.data;
      const detailMessage =
        typeof responseData?.details === "string"
          ? responseData.details
          : responseData?.details?.message;
      const validationMessage =
        responseData &&
        typeof responseData === "object" &&
        Object.values(responseData)
          .flatMap((value) => (Array.isArray(value) ? value : []))
          .filter((value) => typeof value === "string")
          .join(" ");

      console.error("PDF upload failed:", {
        endpoint: `${API.defaults.baseURL}pdfs/`,
        origin: window.location.origin,
        response: responseData,
        message: err.message,
      });

      if (responseData) {
        setError(
          [
            responseData.message ||
              responseData.detail ||
              responseData.error ||
              validationMessage ||
              (typeof responseData === "string" && responseData) ||
              err.message ||
              "PDF upload failed.",
            responseData.stage && `Stage: ${responseData.stage}.`,
            responseData.code && `Code: ${responseData.code}.`,
            detailMessage,
          ]
            .filter(Boolean)
            .join(" ")
        );
      } else if (err.request) {
        setError(
          `No response from the API at ${API.defaults.baseURL}. Check that the backend is running, VITE_API_BASE_URL is correct, and this frontend origin (${window.location.origin}) is allowed by CORS. HTTPS frontends also require an HTTPS API. Browser error: ${err.message}`
        );
      } else {
        setError(err.message || "PDF upload failed. Please try again.");
      }

    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-card">

      <div className="upload-icon">
        <UploadCloud size={35} />
      </div>

      <h2>Upload your PDF</h2>

      <p>
        Upload a document and start asking questions
        with your AI assistant.
      </p>

      <label className="file-select-btn">
        <UploadCloud size={18} />
        Choose PDF

        <input
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          hidden
        />
      </label>

      {file && (
        <div className="selected-file">
          <FileText size={20} />
          <span>{file.name}</span>
        </div>
      )}

      <button
        className="upload-btn"
        onClick={handleUpload}
        disabled={!file || loading}
      >
        {loading ? (
          <>
            <LoaderCircle className="spin" size={18} />
            Uploading PDF...
          </>
        ) : (
          "Upload and Start Chat"
        )}
      </button>

      {error && (
        <p className="upload-error">{error}</p>
      )}

      <small>PDF files only · Maximum size 10 MB</small>

    </div>
  );
};

export default Pdf_uploader;
