
import React, { useState, useEffect, useRef } from "react";

import API from "../../api/axiosInstance";

import {
  Send,
  Sparkles,
  FileText,
  LoaderCircle,
} from "lucide-react";

import Message from "../Message/Message";
import "./ChatWindow.css";

const ChatWindow = ({
  documentId,
  chatId,
  messages = [],
  onMessagesChange,
}) => {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);

  const bottomRef = useRef(null);

  // =====================================
  // 1. SCROLL TO LATEST MESSAGE
  // =====================================

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  // =====================================
  // 2. RESET INPUT WHEN CHAT CHANGES
  // =====================================

  useEffect(() => {
    setQuestion("");
    setLoading(false);
  }, [chatId, documentId]);

  // =====================================
  // 3. ADD MESSAGE TO CURRENT CHAT
  // =====================================

  const addMessage = (targetChatId, newMessage) => {
    if (typeof onMessagesChange !== "function") {
      console.error("onMessagesChange callback is missing!");
      return;
    }

    onMessagesChange(targetChatId, (previousMessages) => [
      ...previousMessages,
      newMessage,
    ]);
  };

  // =====================================
  // 4. SEND MESSAGE TO DJANGO
  // =====================================

  const sendMessage = async () => {
    const userQuestion = question.trim();

    if (!userQuestion || loading) {
      return;
    }

    if (!documentId) {
      addMessage(chatId, {
        sender: "ai",
        text: "Please upload a PDF first.",
      });
      return;
    }

    const validDocumentId = Number(documentId);

    if (
      !Number.isInteger(validDocumentId) ||
      validDocumentId <= 0
    ) {
      addMessage(chatId, {
        sender: "ai",
        text: "Invalid PDF document ID. Please upload the PDF again.",
      });
      return;
    }

    // Store the current chat ID before making the API request.
    // This ensures the answer goes to the correct conversation.
    const currentChatId = chatId;

    // Add user's question to the selected conversation.
    addMessage(currentChatId, {
      sender: "user",
      text: userQuestion,
    });

    setQuestion("");
    setLoading(true);

    try {
      console.log("Sending PDF chat request...");
      console.log("Document ID:", validDocumentId);
      console.log("Chat ID:", currentChatId);
      console.log("Question:", userQuestion);

      const response = await API.post("chat/", {
        document_id: validDocumentId,
        question: userQuestion,
      });

      console.log("Chat response:", response.data);

      const aiAnswer =
        response.data?.answer ||
        "Sorry, I could not generate an answer.";

      // Save the AI response to the original conversation.
      addMessage(currentChatId, {
        sender: "ai",
        text: aiAnswer,
        sources: response.data?.sources || [],
      });

    } catch (error) {
      console.error("Chat API error:", error);

      console.error(
        "Backend status:",
        error.response?.status
      );

      console.error(
        "Backend response:",
        error.response?.data
      );

      let errorText = "Unable to connect to Django backend.";

      if (error.response?.status === 404) {
        errorText =
          "Chat API not found. Please check your Django URLs.";
      } else if (error.response?.status === 400) {
        errorText =
          error.response.data?.details ||
          error.response.data?.error ||
          "Invalid request. Check the PDF ID and question.";
      } else if (error.response?.status === 500) {
        errorText =
          error.response.data?.details ||
          error.response.data?.error ||
          "AI server error. Check your Django terminal.";
      } else if (error.code === "ERR_NETWORK") {
        errorText =
          "Cannot connect to Django. Make sure the backend is running.";
      } else if (error.response?.data?.details) {
        errorText = error.response.data.details;
      } else if (error.response?.data?.error) {
        errorText = error.response.data.error;
      } else if (error.message) {
        errorText = error.message;
      }

      addMessage(currentChatId, {
        sender: "ai",
        text: `⚠️ ${errorText}`,
      });

    } finally {
      setLoading(false);
    }
  };

  // =====================================
  // 5. HANDLE ENTER KEY
  // =====================================

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  // =====================================
  // 6. SUGGESTED QUESTIONS
  // =====================================

  const suggestions = [
    "Summarize this PDF",
    "What are the main topics?",
    "Explain this document simply",
  ];

  // =====================================
  // 7. UI
  // =====================================

  return (
    <div className="chat-window">

      {/* HEADER */}

      <div className="chat-header">
        <div>
          <div className="chat-header-title">
            <Sparkles size={20} />
            <h2>AI PDF Assistant</h2>
          </div>

          <p>
            Ask questions and get answers from your document
          </p>
        </div>

        <div className="online-status">
          <span></span>
          AI Ready
        </div>
      </div>

      {/* CHAT MESSAGES */}

      <div className="chat-messages">

        {messages.length <= 1 && (
          <div className="welcome-section">

            <div className="welcome-icon">
              <FileText size={30} />
            </div>

            <h2>What would you like to know?</h2>

            <p>
              Ask questions about your uploaded PDF.
              I'll find relevant information and answer using its content.
            </p>

            <div className="suggestion-list">

              {suggestions.map((item, index) => (
                <button
                  key={index}
                  onClick={() => setQuestion(item)}
                  disabled={loading}
                >
                  {item}
                </button>
              ))}

            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <Message
            key={`${chatId}-${index}`}
            message={message}
          />
        ))}

        {loading && (
          <div className="typing-indicator">
            <LoaderCircle className="spin" size={18} />
            AI is thinking...
          </div>
        )}

        <div ref={bottomRef} />

      </div>

      {/* MESSAGE INPUT */}

      <div className="chat-input-section">

        <div className="chat-input-box">

          <textarea
            value={question}
            onChange={(event) =>
              setQuestion(event.target.value)
            }
            onKeyDown={handleKeyDown}
            placeholder={
              documentId
                ? "Ask anything about your PDF..."
                : "Upload a PDF to start chatting..."
            }
            rows={1}
            disabled={loading}
          />

          <button
            onClick={sendMessage}
            disabled={!question.trim() || loading}
            className="send-btn"
            aria-label="Send message"
          >
            {loading ? (
              <LoaderCircle className="spin" size={19} />
            ) : (
              <Send size={19} />
            )}
          </button>

        </div>

        <p className="input-footer">
          AI can make mistakes. Verify important information with your document.
        </p>

      </div>

    </div>
  );
};

export default ChatWindow;
