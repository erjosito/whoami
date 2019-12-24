<!DOCTYPE html>
<html lang="en">
    <head>
        <title>Sample container</title>
        <meta charset="utf-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="Description" lang="en" content="Azure VM Info Page">
        <meta name="author" content="Jose Moreno">
        <meta name="robots" content="index, follow">
        <!-- icons -->
        <link rel="apple-touch-icon" href="apple-touch-icon.png">
        <link rel="shortcut icon" href="favicon.ico">
        <!-- CSS file -->
        <link rel="stylesheet" href="styles.css">
    </head>
    <body>
        <div class="header">
			<div class="container">
				<h1 class="header-heading">Welcome to <?php $hostname = exec('hostname'); print($hostname); ?></h1>
			</div>
		</div>
		<div class="nav-bar">
			<div class="container">
				<ul class="nav">
                <li><a href="index.php">Home</a></li>
                    <li><a href="info.php">Info</a></li>
					<li><a href="healthcheck.html">HTML healthcheck</a></li>
					<li><a href="healthcheck.php">PHPinfo</a></li>
					<li><a href="https://github.com/erjosito">My Github repos</a></li>
				</ul>
			</div>
		</div>

		<div class="content">
			<div class="container">
				<div class="main">
					<h1><?php echo exec('hostname'); ?></h1>

                    <h3>Information retrieved from API <?php print(getenv("API_URL")); ?>:</h3>
                    <p>These links will only work if the environment variable API_URL is set to the correct instance of an instance of the image erjosito/sqlapi:</p>
                    <ul>
                    <?php
                        $cmd = "curl " . getenv("API_URL") . "/healthcheck";
                        $result_json = shell_exec($cmd);
                        $result = json_decode($result_json, true);
                        $healthcheck = $result["health"];
                    ?>
                        <li>Healthcheck: <?php print ($healthcheck); ?></li>
                    <?php
                        $cmd = "curl " . getenv("API_URL") . "/sql";
                        $result_json = shell_exec($cmd);
                        $result = json_decode($result_json, true);
                        $sql_output = $result["sql_output"];
                    ?>
                        <li>SQL output: <?php print($sql_output); ?></li>
                    </ul>
                    <br>
                    <h3>Direct access to API</h3>
                    <p>These links will only work if used with an ingress controller</p>
                    <ul>
                        <li><a href='/api/healthcheck'>API health status</a></li>
                        <li><a href='/api/sql'>Database version</a></li>
                    </ul>
                </div>
            </div>
        </div>
        <div class="footer">
            <div class="container">
                &copy; Copyleft 2020
            </div>
        </div>
    </body>
</html>
