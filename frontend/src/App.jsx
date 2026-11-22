
import React, { useEffect, useState } from "react";

import Sidebar from "./Components/Sidebar/Sidebar.jsx";
import Pdf_uploader from "./Components/Pdf_uploader/Pdf_uplaoder.jsx";
import ChatWindow from "./Components/ChatWindow/ChatWindow.jsx";
import API from "./api/axiosInstance.js";

import "./App.css";

// Create a new conversation
const createChat = () => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  title: "New Chat",
  document: null,
  messages: [
    {
      sender: "ai",
      text: "Your PDF is ready! Ask me anything about your uploaded document.",
    },
  ],
});

function App() {
  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    let isMounted = true;

    const checkApiStatus = async () => {
      try {
        const response = await API.get("health/", { timeout: 8000 });
        if (isMounted) {
          setApiStatus(response.data?.status === "ok" ? "online" : "offline");
        }
      } catch {
        if (isMounted) {
          setApiStatus("offline");
        }
      }
    };

    checkApiStatus();
    const intervalId = window.setInterval(checkApiStatus, 30000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  // Current uploaded PDF
  const [document, setDocument] = useState(null);

  // All previous conversations
  const [chats, setChats] = useState([]);

  // Currently selected chat
  const [activeChatId, setActiveChatId] = useState(null);

  // =====================================
  // 1. HANDLE PDF UPLOAD
  // =====================================

  const handleUpload = (uploadedDocument) => {
    if (!uploadedDocument?.id) {
      console.error("Document ID is missing:", uploadedDocument);
      return;
    }

    console.log("PDF uploaded successfully:", uploadedDocument);

    setDocument(uploadedDocument);

    // Create a new conversation for this PDF
    const newChat = {
      ...createChat(),
      document: uploadedDocument,
    };

    setChats((previousChats) => [
      newChat,
      ...previousChats,
    ]);

    setActiveChatId(newChat.id);
  };

  // =====================================
  // 2. HANDLE NEW CHAT
  // =====================================

  const handleNewChat = () => {
    // Clear current uploaded PDF
    setDocument(null);

    // Reset active conversation
    setActiveChatId(null);

    // Keep previous chats in history
    // Do not delete existing chats

    console.log("New chat started. Upload a new PDF.");
  };

  // =====================================
  // 3. SELECT OLD CHAT
  // =====================================

  const handleSelectChat = (chatId) => {
    const selectedChat = chats.find(
      (chat) => chat.id === chatId
    );

    if (!selectedChat) {
      return;
    }

    setActiveChatId(chatId);

    // Restore the PDF associated with that conversation
    setDocument(selectedChat.document || null);
  };

  // =====================================
  // 4. UPDATE CHAT MESSAGES
  // =====================================

  const handleMessagesChange = (chatId, updater) => {
    setChats((previousChats) =>
      previousChats.map((chat) => {
        if (chat.id !== chatId) {
          return chat;
        }

        const updatedMessages =
          typeof updater === "function"
            ? updater(chat.messages)
            : updater;

        const firstUserMessage = updatedMessages.find(
          (message) => message.sender === "user"
        );

        return {
          ...chat,
          messages: updatedMessages,
          title: firstUserMessage
            ? firstUserMessage.text.slice(0, 30)
            : "New Chat",
        };
      })
    );
  };

  // =====================================
  // 5. CLEAR CURRENT CHAT
  // =====================================

  const handleClearChat = () => {
    if (!activeChatId) {
      return;
    }

    handleMessagesChange(activeChatId, () => [
      {
        sender: "ai",
        text: "Your conversation has been cleared. Ask me anything about your PDF.",
      },
    ]);
  };

  // =====================================
  // 6. GET ACTIVE CHAT
  // =====================================

  const activeChat = chats.find(
    (chat) => chat.id === activeChatId
  );

  // =====================================
  // 7. RENDER UI
  // =====================================

  return (
    <div className="app-container">
      <div
        className={`api-status api-status--${apiStatus}`}
        role="status"
        aria-live="polite"
      >
        <span className="api-status-dot" aria-hidden="true" />
        {apiStatus === "checking"
          ? "Checking server"
          : apiStatus === "online"
            ? "Server online"
            : "Server offline"}
      </div>

      <Sidebar
        document={document}
        chatSessions={chats}
        activeChatId={activeChatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onClearChat={handleClearChat}
      />

      <main className="main-content">

        {!document ? (

          // Show PDF uploader for a new chat
          <div className="upload-page">

            <div className="upload-page-header">
              <h1>Welcome to AI PDF Assistant</h1>

              <p>
                Upload your PDF and chat with your document.
              </p>
            </div>

            <Pdf_uploader onUpload={handleUpload} />

          </div>

        ) : activeChat ? (

          // Show selected conversation
          <ChatWindow
            key={activeChat.id}
            chatId={activeChat.id}
            documentId={document.id}
            messages={activeChat.messages}
            onMessagesChange={handleMessagesChange}
          />

        ) : (

          <div className="upload-page">
            <h2>Select a chat or create a new chat.</h2>
          </div>

        )}

      </main>
    </div>
  );
}

export default App;
