import React, { useState, useEffect } from "react";
import "./App.css";

function App() {
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    fetchTasks();
  }, []);

  const fetchTasks = async () => {
    const response = await fetch("/api/tasks");
    const data = await response.json();
    setTasks(data.tasks);
  };

  const addTask = async () => {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: {
        "Content-Type": "application/json", // 👈 关键：告诉后端我发的是JSON
      },
      body: JSON.stringify({
        title: title,
        description: description,
      }),
    });
    const data = await response.json();
    setTasks([...tasks, data.task]);
    setTitle("");
    setDescription("");
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>TaskFlow</h1>
      </header>
      <main>
        <div>
          <input
            type="text"
            placeholder="Task title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            type="text"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button onClick={addTask}>Add Task</button>
        </div>
        <ul>
          {tasks.map((task) => (
            <li key={task.id}>
              <h3>{task.title}</h3>
              <p>{task.description}</p>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}

export default App;
