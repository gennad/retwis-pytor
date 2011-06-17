$(document).ready(function() {
    document.getElementById('status').onkeyup = function(e){
        e = e || event;
        if (e.keyCode === 13 && e.ctrlKey) {
            document.status_form.submit();
        }
        return true;
    }
});
