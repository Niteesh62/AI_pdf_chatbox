
import React from "react";
import {
  Bot,
  MessageSquare,
  Plus,
  Trash2,
  FileText,
  Sparkles,
} from "lucide-react";

import "./Sidebar.css";

const Sidebar = ({
  document = null,
  chatSessions = [],
  activeChatId = null,
  onNewChat,
  onSelectChat,
  onClearChat,
}) => {
  const handleNewChat = () => {
    if (onNewChat) {
      onNewChat();
    }
  };

  return (
    <aside className="sidebar">

      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-icon">
          <Bot size={25} />
        </div>

        <div>
          <h2>PDF Assistant</h2>
          <p>AI Document Chat</p>
        </div>
      </div>

      {/* New Chat */}
      <button
        type="button"
        className="new-chat-btn"
        onClick={handleNewChat}
      >
        <Plus size={18} />
        <span>New Chat</span>
      </button>

      {/* Workspace */}
      <div className="sidebar-section">
        <p className="section-heading">WORKSPACE</p>

        <div className="sidebar-menu-item active">
          <MessageSquare size={18} />
          <span>PDF Chat</span>
        </div>
      </div>

      {/* Chat History */}
      <div className="sidebar-section chat-history-section">
        <p className="section-heading">CHAT HISTORY</p>

        {chatSessions.length > 0 ? (
          <div className="chat-history-list">

            {chatSessions.map((chat) => (
              <button
                type="button"
                key={chat.id}
                className={`chat-history-item ${
                  activeChatId === chat.id ? "active" : ""
                }`}
                onClick={() => onSelectChat?.(chat.id)}
                title={chat.title || "New Chat"}
              >
                <MessageSquare size={17} />

                <span>
                  {chat.title || "New Chat"}
                </span>
              </button>
            ))}

          </div>
        ) : (
          <p className="no-document">
            No previous chats
          </p>
        )}
      </div>

      {/* Current Document */}
      <div className="sidebar-section">
        <p className="section-heading">CURRENT DOCUMENT</p>

        {document ? (
          <div className="document-info">
            <FileText size={20} />

            <div>
              <p>
                {document.title || document.name || "Untitled PDF"}
              </p>
              <span>PDF uploaded</span>
            </div>
          </div>
        ) : (
          <p className="no-document">
            No document uploaded
          </p>
        )}
      </div>

      {/* Bottom Section */}
      <div className="sidebar-bottom">

        <div className="sidebar-tip">
          <Sparkles size={18} />

          <div>
            <strong>AI Assistant</strong>
            <p>Ask questions about your PDF.</p>
          </div>
        </div>

        <button
          type="button"
          className="clear-chat-btn"
          onClick={onClearChat}
          disabled={!activeChatId}
        >
          <Trash2 size={17} />
          <span>Clear conversation</span>
        </button>

      </div>

    </aside>
  );
};

export default Sidebar;
