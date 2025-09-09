const commands = {
    "dump": {},
    "login": { "id": "str" },
    "logout": {},
    "add_user": { "id": "str", "name": "str", "su": "bool" }
};

document.addEventListener('DOMContentLoaded', () => {
    const commandList = document.getElementById('command-list');
    const resultField = document.createElement('textarea'); // Create a text area for results
    resultField.id = 'result-field';
    resultField.rows = 5;
    resultField.cols = 50;
    resultField.readOnly = true; // Make it read-only
    resultField.placeholder = 'Results of REST calls will appear here...';
    document.body.insertBefore(resultField, commandList); // Add it before the command list

    for (const command in commands) {
        const button = document.createElement('button');
        button.textContent = command;
        button.onclick = () => showForm(command);
        commandList.appendChild(button);
    }
});

function showForm(command) {
    const formContainer = document.getElementById('command-form');
    formContainer.innerHTML = ''; // Clear existing form fields

    const commandData = commands[command];
    for (const key in commandData) {
        const formGroup = document.createElement('div');
        formGroup.className = 'form-group';

        const label = document.createElement('label');
        label.textContent = key;
        formGroup.appendChild(label);

        const input = document.createElement('input');
        input.type = 'text';
        input.name = key;
        formGroup.appendChild(input);

        formContainer.appendChild(formGroup);
    }

    const sendButton = document.createElement('button');
    sendButton.type = 'submit';
    sendButton.textContent = 'Send';
    formContainer.appendChild(sendButton);

    formContainer.setAttribute('data-command', command);
}

function sendForm(event) {
    event.preventDefault();
    const formContainer = document.getElementById('command-form');
    const command = formContainer.getAttribute('data-command');
    const formData = new FormData(formContainer);
    const payload = {};
    const commandData = commands[command];
    for (const key in commandData) {
        const value = formData.get(key);
        if (commandData[key] === 'bool') {
            payload[key] = value === 'true';
        } else {
            payload[key] = value;
        }
    };

    console.log(command + " : " + JSON.stringify(payload));
    fetch(`http://localhost:5000/${command}`, {
        method: 'POST',
        mode: 'cors', // Set the mode to 'cors'
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify(payload) // Convert payload to JSON string
    })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
            document.getElementById('result-field').value = JSON.stringify(data, null, 2); // Display result in the text area
        })
        .catch((error) => {
            console.error('Error:', error);
            document.getElementById('result-field').value = `Error: ${error.message}`; // Display error in the text area
        });
}