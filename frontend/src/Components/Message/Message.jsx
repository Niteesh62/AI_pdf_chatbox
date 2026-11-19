import React from "react";
import { User, Bot, FileText } from "lucide-react";

import "../Message/Message.css";

const Message = ({ message }) => {
  const isUser = message.sender === "user";

  return (
    <div className={`message-row ${isUser ? "user-row" : "ai-row"}`}>

      <div className={`message-avatar ${isUser ? "user-avatar" : "ai-avatar"}`}>
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>

      <div className="message-content">

        <div className="message-name">
          {isUser ? "You" : "AI Assistant"}
        </div>

        <div className={`message-bubble ${isUser ? "user-bubble" : "ai-bubble"}`}>
          {message.text}
        </div>

        {message.sources?.length > 0 && (
          <div className="message-sources">
            <FileText size={14} />

            <span>
              Sources: Page {message.sources.join(", ")}
            </span>
          </div>
        )}

      </div>

    </div>
  );
};

export default Message;